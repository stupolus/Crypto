export const meta = {
  name: 'claude-council',
  description: 'Council of independent Claude agents: parallel opinions, anonymized peer review, results handed to the chairman for synthesis',
  whenToUse: 'Invoked by the llm-council skill when the user asks to consult the council or wants multiple independent AI perspectives',
  phases: [
    { title: 'Opinions', detail: 'council members answer independently in parallel' },
    { title: 'Peer Review', detail: 'each member critiques and ranks the anonymized answers' },
  ],
}

// args may arrive as a parsed object, a JSON-encoded string, or a bare question string
let input = args
if (typeof input === 'string') {
  try { input = JSON.parse(input) } catch (e) { input = { question: input } }
}
if (!input || typeof input !== 'object' || Array.isArray(input)) {
  throw new Error('args must be {question, mode?, context?, members?} or a question string')
}
const question = input.question
if (!question || typeof question !== 'string') throw new Error('args.question (string) is required')
const mode = input.mode === 'quick' ? 'quick' : 'full'
const extraContext = input.context
  ? `\n\nADDITIONAL CONTEXT (from the user's session):\n${input.context}`
  : ''

const IDS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
const MODELS = ['fable', 'opus', 'sonnet', 'haiku']

// NOTE (verified 2026-06-11): subagents cannot run Fable 5 — model:'fable' silently
// falls back to Opus 4.8 (confirmed via agent transcript model IDs). Defaults pin
// 'opus' so labels match reality; 'fable' stays accepted in MODELS for the day
// subagent support lands — flip the Architect/Skeptic back to it then.
const DEFAULT_MEMBERS = [
  {
    persona: 'The Architect',
    model: 'opus',
    brief: 'Systems design and long-term consequences: interfaces, data flow, coupling, scalability, maintainability, and how the solution evolves and survives changing requirements.',
  },
  {
    persona: 'The Skeptic',
    model: 'opus',
    brief: 'Adversarial review: question the premise of the question itself, surface risks, hidden costs, edge cases and failure modes, and identify the strongest alternative the asker has probably not considered. If the council is being asked the wrong question, say what the right question is.',
  },
  {
    persona: 'The Pragmatist',
    model: 'opus',
    brief: 'Shipping: the simplest thing that could possibly work, time-to-value, what to cut, where YAGNI applies, and the smallest first step that de-risks the rest. Concrete steps over abstractions.',
  },
  {
    persona: 'The Researcher',
    model: 'opus',
    brief: 'Evidence and prior art: established solutions, libraries, papers, and best practices that already address this. Verify what you cite (use web search when it helps) and name names: tools, versions, references.',
  },
]

const rawMembers = Array.isArray(input.members) && input.members.length >= 2
  ? input.members
  : DEFAULT_MEMBERS
const members = rawMembers.slice(0, IDS.length).map((m, i) => ({
  id: IDS[i],
  persona: (m && m.persona) || `Member ${IDS[i]}`,
  model: m && MODELS.includes(m.model) ? m.model : 'opus',
  brief: (m && m.brief) || 'A thoughtful, independent expert perspective.',
}))

const OPINION_SCHEMA = {
  type: 'object',
  properties: {
    stance: { type: 'string', description: 'Your position in one sentence' },
    answer: { type: 'string', description: 'Your full answer/recommendation in markdown, under ~600 words' },
    key_points: { type: 'array', items: { type: 'string' }, description: 'The 3-6 most important points' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
  },
  required: ['stance', 'answer', 'key_points', 'confidence'],
}

const opinionPrompt = (m) => `You are "${m.persona}", one of ${members.length} independent members of an advisory council. Every member answers the same question in isolation; your answer will later be critiqued and ranked anonymously by the other members, so make it count.

YOUR LENS: ${m.brief}

THE QUESTION:
${question}${extraContext}

Ground rules:
- You are running in the user's current project directory. If the question concerns this project or its code, investigate the relevant files with your tools before opining. If it is a general question, answer directly without exploring.
- Use web search only if current or external facts would materially improve the answer.
- Take a clear position with concrete recommendations. Hedged mush gets ranked last in peer review.
- Stay true to your lens, but do not be a caricature: if the evidence goes against your natural inclination, say so.`

phase('Opinions')
log(`Convening council of ${members.length}: ${members.map((m) => m.persona).join(', ')} (mode: ${mode})`)
const opinionResults = await parallel(members.map((m) => () =>
  agent(opinionPrompt(m), { label: m.persona, phase: 'Opinions', model: m.model, schema: OPINION_SCHEMA })
    .then((op) => (op ? { member: m, opinion: op } : null))
))
const seated = opinionResults.filter(Boolean)
if (seated.length === 0) throw new Error('No council member returned an opinion')
if (seated.length < members.length) {
  log(`${members.length - seated.length} member(s) failed to respond; proceeding with ${seated.length}`)
}

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    critiques: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          response_id: { type: 'string', description: 'The single-letter response ID, e.g. "A"' },
          strengths: { type: 'string' },
          weaknesses: { type: 'string' },
        },
        required: ['response_id', 'strengths', 'weaknesses'],
      },
    },
    ranking: { type: 'array', items: { type: 'string' }, description: 'All response IDs ordered best to worst, e.g. ["B","A","D","C"]' },
    best_overall_insight: { type: 'string', description: 'The single most valuable insight across all responses' },
  },
  required: ['critiques', 'ranking'],
}

let reviews = []
if (mode === 'full' && seated.length >= 2) {
  phase('Peer Review')
  const validIds = seated.map((s) => s.member.id)
  const packet = seated
    .map((s) => `### Response ${s.member.id}\n\nStance: ${s.opinion.stance}\n\n${s.opinion.answer}`)
    .join('\n\n---\n\n')
  const reviewPrompt = (m) => `You are "${m.persona}" serving as a peer reviewer on an advisory council. The council was asked:

${question}${extraContext}

Below are the ${seated.length} anonymized answers from the council. One of them may be your own — judge it as harshly as the rest.

${packet}

For EACH response, give its main strengths and weaknesses. Then rank ALL responses from best to worst by: correctness, insight density, actionability, and how well it answers the actual question (not how well it matches your own style). Use response_id values exactly from: ${validIds.join(', ')}. Judge only what is written — do not explore the filesystem or web.`

  const reviewResults = await parallel(seated.map((s) => () =>
    agent(reviewPrompt(s.member), { label: `review by ${s.member.persona}`, phase: 'Peer Review', model: s.member.model, schema: REVIEW_SCHEMA })
      .then((rv) => (rv ? { reviewer: s.member.persona, reviewer_id: s.member.id, review: rv } : null))
  ))
  reviews = reviewResults.filter(Boolean)
  if (reviews.length === 0) log('Peer review round returned nothing; falling back to opinions only')
}

const validIdSet = new Set(seated.map((s) => s.member.id))
const normalizeId = (x) => {
  const cleaned = String(x).replace(/response/i, '').replace(/[^a-z]/gi, '').toUpperCase()
  return validIdSet.has(cleaned) ? cleaned : null
}
const rankSums = {}
const rankCounts = {}
for (const r of reviews) {
  const seen = new Set()
  const ranked = (r.review.ranking || [])
    .map(normalizeId)
    .filter((id) => id && !seen.has(id) && seen.add(id))
  ranked.forEach((id, pos) => {
    rankSums[id] = (rankSums[id] || 0) + pos + 1
    rankCounts[id] = (rankCounts[id] || 0) + 1
  })
}
const aggregate_ranking = [...validIdSet]
  .map((id) => ({
    id,
    persona: seated.find((s) => s.member.id === id).member.persona,
    average_rank: rankCounts[id] ? Math.round((rankSums[id] / rankCounts[id]) * 100) / 100 : null,
    times_ranked: rankCounts[id] || 0,
  }))
  .sort((a, b) => (a.average_rank == null ? 99 : a.average_rank) - (b.average_rank == null ? 99 : b.average_rank))

log('Council adjourned — handing results to the chairman')
return {
  question,
  mode,
  members_failed: members.length - seated.length,
  council: seated.map((s) => ({
    id: s.member.id,
    persona: s.member.persona,
    model: s.member.model,
    stance: s.opinion.stance,
    confidence: s.opinion.confidence,
    key_points: s.opinion.key_points,
    answer: s.opinion.answer,
  })),
  peer_reviews: reviews,
  aggregate_ranking,
  synthesis_instructions: 'Chairman (main session): de-anonymize, synthesize the final plan with inline attribution, include the council verdict table and consensus/dissent notes per SKILL.md Stage 3.',
}
