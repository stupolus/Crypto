# I turned Claude Opus into a 24/7 crypto trader for a week... (insane results)

- video: https://youtu.be/5q9pClfX-Io
- lang: en
- source: automatic_captions (сырой ASR, черновик)

---

So if you come over to the Anthropic website, you can see the introduction of Claude Opus 4.7, the
cuttingedge smartest AI model currently out there, comes equipped with benchmark testing. This is
what AI companies always do when they release the latest model. They benchmark test it in a bunch of
categories and compare it not only to their last model, but to the competitors models that are the
cuttingedge models for those companies. And if we take a peek down here at the Agentic Financial
Analysis stat, you can see we currently have in Opus 4.7 the highest score we've ever received. Your
own personal finance agent now at least 10% sharper than most the other models. And because here on
this channel, we have been trading with AI agents who we literally equip with our crypto wallets,
equip with cutting edge strategies, and send them out to the trenches to trade on our behalfs with
historically excellent results. I want to know what happens if we upgrade the brain of these agents
to Opus 4.7. So, in this video, we gave three different AI agents, all powered by Opus 4.7, $10,000
each, and 7 days to see how much money they could make by trading with this overpowered brain. This
video and all other videos on this channel are for entertainment purposes only. Modern financial
instruments, including crypto, are highly volatile, and the majority of retail clients will lose
money. Do not invest any capital you're not prepared to go to zero. Now, there's a few AI YouTubers,
including this lovely man right here, Nate Herk, who might just be the biggest AI YouTuber there is,
growing extremely fast at 739,000 subs, who are now starting to get into using Claude to actually
trade. In fact, this was the video down here that I watched, 33 minutes, verified by this red bar
right here, where I mean, this got 403,000 views, which compared to his other videos is like a four
to 5x multiple on all of his other videos. But I've been watching a lot of these videos and
including Net Herk, they have a very clunky setup that is not optimized based on everything we've
learned over the last 5 months of trading with AI agents. In fact, I want to walk you through
exactly what Nate Herk's doing and why it's not optimal. And then I'm going to show you exactly how
we run our agents and why it's so much better. But I'll let you decide for yourself. So this is Nate
Herk setup from the video. He has Opus 4.7, the super overpowered brain of the operation. And then
this LLM is plugged into an MD file. Now, this MD file is trading instructions and strategy. So,
basically, it's a markdown file, just a bunch of text. LLM wakes up. There's like, oh, hello. Where
am I? Oh, here's a file for me to read. Sort of like 50 first dates where they read what their life
is. He reads that he's a trader. He reads the types of strategy that he's using. And he does it on a
chron job, which is I think it stands for chronological job, which happens five times every 24
hours. He prompts his agent to wake up, read the brain file, head over to an alpaca API, which is
the stock trading platform that he's using, make the trades, and then log it, and basically log
everything that he's doing, which this part of it is actually excellent because you get to machine
learn based on your past trades, which ones did well, which ones didn't, and review and then feed it
back into the LLM. However, there are four five in fact flaws with this plan. And even when I looked
at Nate's results, like he was talking about getting a negative.2% over a 30-day period and saying
it's way better because the S&P got negative 8%. But I'm like, yeah, we don't want the world's
smartest traders pulling in a negative.2%. And so these reasons below are where he went wrong
because he's not actually even factoring in API costs because you're actually getting the AI to
operate on your behalf. He is not just the brains, but he's the hands of the operation, which is
going to cost you a lot. Also, trading costs with the Alpaca API is going to be costly and cut into
your profit. He only has his agent, his superpower agent, is only awake five times a day, very
fleetatingly, to make a trade and then go back to sleep. So, he's not actually got a 24/7 bot. In
fact, he has a five times a day bot. And if he's not waking up at the right time, he would have
missed a lot of trades. extremely costly also because his AI is not just the brain but the hands of
the operation it is overprotective. Remember AI is trained on the entire data set of the internet
and humans are very emotional creatures and even when they trade they're using a lot of emotion and
if it's learning on this it's going to get scared to trade. We've seen this so many times where our
AI agents like oh I saw this really good trade opening but I didn't because I wanted to protect our
capital. It's like no that's not the strategy. It cannot deviate from the strategy if AI is not the
hands. I'm going to show you exactly how we overcome that problem ourselves. And this is very heavy
infrastructure. Every time this wakes up, it has to reread the files. It starts from zero every
single time. And it's very hard to scale and very costly. And of course, that's why it leads to a
negative result over 30 days. Now, this is a way superior strategy that we've literally taken months
to crunch down. And I want to show you the results of it at the end of this video as well. So, we
use a platform. Everyone in the comments is like, I have an accent, an Australian accent. So, I say
lighter. We trade on the lighter platform. Everyone's like, "When's he going to stop gatekeeping
this platform?" We're not sponsored by them. Their name is lighter. They have zero fees. So, it's
already a massive improvement on trading on something like Hyperlid or even Alpaca API. Now, we have
our AI over here in the corner. Let's start with this. This is Opus 4.7, the smartest model, the one
that scored the highest on the financial analysis. It is AI that is refining using walk forward back
testing. Meaning we're not just checking that this worked in the past. We are actually testing the
strategies and the best strategies in the world to see that they're still working in the present.
And they have years of data and they machine learn to perfect the strategy. And in fact, they pick
from a bunch of different strategies. The one we use in this video is called the ton mass index
reversal which we'll show you very soon. And so how this workflow actually happens is we are pulling
the data from lighter which is where we're actually going to be trading from because if you're not
trading on the same platform and there's differences you could run into some big costly problems. So
we're pulling all the data and feeding it into the winning strategy script. Now this script is being
shaped by the world's smartest AI and constantly refining it and learning based on not just back
testing but actual live data and how its trades are going. And when the LLM and winning script hits
the formula, so they say these are the rules. For example, this is the actual way that we were
trading when the mass index is greater than 27 and current close is greater than previous close and
then short it if it's the opposite of that. This is the stop-loss. This is so this is basically the
rules, the winning formula. And you can see if you want to have a look what that actually means in
English, you can pause it and read this right here on exactly what the mass index and everything
means. But this here is not AI. This is a script created by AI and that is the big difference
because it can execute flawlessly with no emotion and anytime the setup is there 24/7 it can execute
without the AI having to wake up and actually execute for it. Then we have an execution script that
it passes it off to which is connected to our crypto wallet. And so this setup which we refined over
months and have got way better results using something like this has no API costs. It has no trading
fee costs. It trades 24 hours a day. There's no human bias and a scalable light infrastructure that
you can literally have hundreds of these running at once, all with different strategies. Now, you do
need somewhere to host something like this. So, you could use a hosting server like Hostinger, which
is the perfect time for a quick word from the sponsor of our video. Hostinger. If you want to run AI
trade bots like these 24/7, you need a server that does not sleep. Not your laptop, not your phone,
a proper cloud server. Normally that means SSH terminal, installing open core manually, plugging in
an LLM, setting up web scraping, a full weekend project. Hostinger just made it one click. Go to the
link in description and pick managed open core plan and it spins up a cloud instance with open core
pre-installed. No config files, no terminal. They've plugged in Nexus AI directly so you can switch
between Claude, GPT, Gemini, and Grock all from one dashboard. Web scraping is also built in too, so
your bots can pull realtime market data without wiring up a separate API and your data stays on your
own isolated Docker container. Go for 12 or 24 months. It's way cheaper than paying monthly. Links
in the description for 70%ish discount. Now, back to the bots. So, using this setup, we gave three
Opus 4.7 agents $10,000 each and 7 days to trade. The only difference between these bots was the
strategy, which is this yellow part over here, where we pulled the most profitable strategies in
crypto over almost a decade and back tested them. So, we had Claude pick from these strategies and
whether they want them flipped or to use the full strategy, which historically has had some crazy
returns for some of these traders. And so, each of our three different agents is being empowered by
a different strategy inside of our bot market. And the results continue to be promising. And I ran
three bots so we can compare these strategies against one another. So we're just going to click play
right here. And you can see after the first two days, the first bot, which is Claude index reversal,
was up. So turning 10 grand into this amount right here, having 15 winning trades and three losses.
The second bot was up even more than that. 32 wins and seven losses. Off to an excellent start. The
third bot, Claude Pivot, however, was not winning as much, although it had more winning trades. the
losing trades were larger amounts. So, it was down 5.8%. To play on for another couple of days all
the way up to day four right here, you can see they basically it looks like they're coasting. It
looks like they're going sideways, but these bots are actually performing extremely well. This
Claude index reversal bot was now up still only having four losses. And this bot, although it had 19
losses, the Claude Momentum Cascade was up as well, while this was still losing. But you know, you
can see there's a lot more profit in these traders right here than what Claude pivot is losing. Then
we click play for another two days and absolute magic occurred. The Claude index reversal, which was
using 20x leveraged, hit a banger all the way up to a $30,86 wallet, still only losing six trades.
The Claude Momentum Cascade was also doing extremely well with 32% up and this bad boy Claude Pivot
was hanging in there at a negative 8% but you know we can take a loss if you can see the other ones
are so far into the green. We continue to play and unfortunately over that next day a lot of Claude
index reversals profits came melting down back to a $21,000 wallet down to a $12,000 wallet and then
Claude Pivot it was not doing well. He was actually trading ETH where this bot was trading on Tao
and this bot over here was trading on Ton. Three different blockchains to trade on. And you can see
ETH was not the winner in this strategy all the way to day eight where it's so fascinating. It
doesn't really matter how many of these bots we run. They seem to even off at the end trying to save
whatever profits they've made or not lose anymore if they were losing. Coming in at 112.6% plus 25%
for the second bot and -10% for the third bot. far out exceeding a negative.2% of what other traders
have got. When you accumulate these together, it was a net portfolio jump. An absolutely incredible
result, which honestly we are really proud of, including this big one right here. You can see it's
more volatile cuz it's using a lot more leverage than the other two bots, which peaked up at this
percentage on day six. Now, if you want to get access to our strategy marketplace and have bots
literally deployed and trading on your behalf using our framework that we walk through in this
video, including on the lighter platform where there are no fees, there's no API costs. You can just
literally come in here, back test a strategy, or you can just come in here and click deploy. Click
the link in the description below to come and join us inside of our inner circle. We literally have
an inner circle here where we have AI constantly out there split testing strategies, finding the
most profitable trading strategies possible and trading on our behalf, even when we're not at the
computer. You can, of course, start with some paper money or you can come in and perhaps start
trading immediately as soon as you sign up with real crypto. The link to our inner circle to get
access to all this is in the description below. Thanks so much for watching and I'll see you in the
next
