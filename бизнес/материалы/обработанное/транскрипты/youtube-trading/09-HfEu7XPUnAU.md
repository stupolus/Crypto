# I Built An Entire AI Trading Team With Claude Code in 14 min

- video: https://youtu.be/HfEu7XPUnAU
- lang: en
- source: automatic_captions (сырой ASR, черновик)

---

Did you guys know that majority of retail traders lose money? And it's not because they're dumb,
it's because they're making decisions based on gut feeling instead of actual research. They see a
stock trending on social media, they throw money at it, and they wonder why they're down 40%. Now,
the problem isn't trading itself, it's that most people don't have a research process. They're not
looking at the technical, the fundamentals, the sentiment, the risk, they're just guessing. So, I
built an AI trading analyst team with Claude code that does all of that research for you completely
for free. It analyzes any stock across five dimensions simultaneously. Technical analysis,
fundamentals, sentiment, risk assessment, and it even builds you a complete investment thesis with
entry and exit points. 16 skills, five AI agents, one command. Now, let me be clear, this is not a
trading bot or financial advice. This does not touch your money, this does not make trades for you.
This is a research tool that gives you the analysis so you can make better decisions. So, in this
video, I'm going to run this on a real stock so you can see exactly what it produces. Then I'm going
to walk you through step-by-step how to install this regardless of your background, so that way you
can run it on any stock you're looking at. And if you're new here, my name is Zubair. I've had my
own AI agency for the past 2 years, and now I run a community teaching other people how to start
theirs. So, with that being said, let's jump right in. All right, so now before I show you how this
works and how to install this, let me show you what this produces because it's amazing. So, I ran
one command on Nvidia, again, that's one command, and it generated this entire investment thesis
report. Thesis score 78 out of 100, strong conviction. Every key metric laid out, revenue growth
73%, net margin 55%, analyst target 49% above current price. It scores across five dimensions,
catalyst clarity, timing, asymmetry, edge, and conviction. Full bull case with price targets, full
bear case with every risk. Again, nothing is sugarcoated here. And look at this, a specific entry
zone, stop loss, three profit targets, position sizing, scaling strategy, and risk-reward ratio.
This is what a hedge fund analyst produces. It even gives you a full risk matrix with probability,
impact, and mitigation for every single threat. Again, this entire report was only generated with
one command using this tool. So, now let me show you how this works. I'm going to run this live on
Tesla, then on another stock so you can see how the results compare, and then I'll break down the
skills, the agents, and how you can install this on your computer completely for free. All right, so
I'm going to click on Claude code here. Again, don't worry if you don't know how to use this, I'm
going to show you exactly how to install this and how to use this inside Claude code. So, what I'm
going to do is enter slash, and I'm going to do trade, and as you can see, all of these skills are
available for me. I'm going to actually scroll down to trade analyze, and just put the Tesla ticker.
And I'm going to press enter. So, now Claude code is going to run this trade analyze skill, which
consists of multiple agents and multiple skills that are all inside the skills.md file. So, it has
multiple phases. The first phase is going to be discovery, searching for Tesla itself. So, as you
can see, that's what it's doing. It's doing web search on Tesla stock price today, the market cap
volume. It's doing the Tesla company overview, business description, the Tesla stock news, latest
news, right? It's going to search all of these different resources, and then the next stage is going
to be running five parallel agents, and all of this is going to happen because the skills.md file,
which is inside this AI trade tool that I'm going to again explain a little bit. So, this trade
analyze, that's exactly what we ran, right? So, it's it's doing the full stock analysis. Phase one
is going to do discovery. Now, phase two is going to be parallel agents. So, it's going to deploy
five different agents. First agent is going to do technical analysis. The second agent is going to
do fundamental analysis. The third agent is going to sentiment analysis. The fourth one, risk
assessment. And the fifth one, thesis synthesis, right? All of these instructions are inside the
skills.md file. So, if we go back, that's exactly what's happening. Right now, as you can see, it's
still going through the discovery phase. So, what I'm going to do is just quickly fast forward this
cuz otherwise it's going to take a couple of minutes so that I can show you the results. And then on
the next one, I'm going to explain all of these skills and all of the agents what's going on. So, as
you can see right here, it says discovery data compiled, now launching five analysis agents in
parallel. So, the first one, second one, third one. So, let me go ahead and fast forward this. And
there you go. So, it completed all of the analysis, the five agents and everything, and it generated
this report. So, if I let let me quickly zoom in here for you guys. So, AI trading analyst report,
Tesla, right? Tesla Inc. Generated April 8, 2026. It gives it this trading score of 43 out of 100,
says caution. So, now I'm going to quickly go through the different PDF sections in a bit more
detail, and then I'm going to show you how to install this and run this yourself. All right, so the
first one is going to be score dashboard, right? This is going to run that show you exactly the
different scores, the weight, the statuses. So, the technical strength, fundamental quality,
sentiment, risk profile, and thesis conviction. All of this is based on those agents that we ran.
You have the technical overview, the key levels, right? It gives you the different levels for the
price resistance, and the notes which one is, you know, 52-week high, the Fibonacci replacement, and
all of these technical things that, you know, are usually an actual analyst in hedge funds go
through actually. So, it gives you the indicator readings, right? Again, like I mentioned before,
this is not an investment tool, it's more of a research tool for you to understand exactly how
everything works and know everything about there is for a particular stock that you're looking at.
So, it gives you the fundamental overview, the key metrics, right? It's going to give you the
valuation assessment, the competitive mode, and then also gives you the investment thesis, the bull
case, the bear case. Again, it's not sugarcoating anything regardless of whatever stock you're
looking at, it's going to give you all of the different information, the positives, the negatives,
and everything else so that way you can be aware of what's going on. It gives you the catalyst
timeline. This is amazing, right? It gives you exactly what are the events that are coming up and
what kind of potential impact it might have in that stock price. It gives you the entry and exit
strategy. It gives you the risk and positioning sizing, right? So, it gives you exactly the risk and
reward analysis, the recommended position size, the max drawdown scenario, the volatility profile,
market correlation, and it also gives you a position sizing methodology, how to position everything
based on the bull case, bear case, and the base case, right? And a bunch of other details you can
pull from this. So, that's with just one skill that we ran, which is the skills trade. Now, inside
this tool itself, so if I go back, so all of these skills that exist, again, there's 16 commands,
and each command does something different. We just ran this trade analyze, right? This is the
flagship command, which is going to do full stock analysis with five agents and returns the trade
score and everything else. You can do a trade quick, this is going to do a 60-second stock snapshot
on a particular stock. So, let's say if you're you just want quick information and not the full
analysis, you run this. You can get a technical technical analysis, you can get the fundamentals.
You can do the trade sentiment based on the news and social sentiment cuz it's going to actually
analyze and research what are the sentiment for that particular stock in the social media, in news,
and everything else that's going on, which is incredibly important because stock market and trading
in general is not just about the technical fundamentals, it's it's also about the perceived value
and also the social sentiment of that company itself. So, the thesis and strategy, again, this is
where you can compare actually head-to-head stock comparison, you can compare different stocks. You
can do trade options. Now, option is obviously the risky one, but it also gives you that information
as well. And then also again, scoring methodology explaining everything, and I have like a little
sample outfall so if you output if you just analyze Apple, it's going to give you all of the
different details, but of course we went through and I showed you exactly what type of PDF reports
it's capable of generating. And it also gives you the use cases, who is this useful for, right? Day
traders, swing traders, long-term investor, option trader, portfolio manager. This is for everybody
because again, this is just a research tool, a pure research tool that gives you all of this data
that usually you would have to do manually, and it would take you a week or two. This is doing it in
one command. Absolutely incredible. We live in amazing time right here. All right, so that's what
basically this tool does. Now, let me show you how to install this so that way you can run this on
whatever stock you're looking at yourself. All right, so first things first, you want to make sure
you have Visual Studio Code installed. Now, again, this is just an IDE because we want to make sure
we run Claude code through here so that way we can have all the files in one cohesive place. This is
completely free, so go ahead and install this. Once you download this, this is what the interface
inter interface, I can't even talk. The interface looks like. So, if I open this Claude code, this
is what this looks like. All your files here on the left-hand side basically is in the folder that
you open here. So, in order to install Claude code, you want to make sure you come to the extension
right here, and you look for Claude code, and you can just install this. Again, this is completely
free, so this is by Anthropic. Make sure you're installing the correct one, and then it will ask you
to connect to your obviously you have to have a paid subscription. So, once you install that, this
little sign right here, this little icon for Claude code is going to be available on top here.
You're going to click on this, and it will open a new instance of Claude code. Now, what you want to
do first of all is create a a new folder. You're going to click on new folder, name it whatever you
want, right? Since I already have this YouTube demo folder, it's going to look something like this.
Now, here's how you can install these skills because as you can see right now, when I press the
slash and do trade, right? All of these skills are available for me. In order to get this, what you
need to do is install I've put all of this together in a nice little zip file for you guys. So, all
you have to do is click on the link in the description. This is the free community that I have,
again, this is completely free. All you have to do is go to the classroom section. You're going to
click on YouTube resources, and you're going to go to Claude code and scroll to the bottom. I have a
bunch of stuff other stuff that I've built here, but you're going to click on this AI trade research
analyst team, and right here in the bottom, I have this zip file. And you're going to download this,
this is going to download the zip file for you, and I'm going to show that in a little bit how you
can put this inside that folder. And if you're part of my paid community, of course, I've made life
very easy for you guys. All you have to do is go to the build and sell course with Claude code, and
you're going to come to the bottom. All you have to do is just copy this. I'm just going to copy
this. It's just one command because you guys have access to the private repo from my GitHub. Um and
you're going to copy this. You're going to go back to your Visual Studio Code. You're going to click
on this terminal, and then all you have to do is just paste that one command. Let me actually make
this a little bigger. Press enter, and it's going to download all of these skills for you, these,
you know, trade analyze technicals and everything else. So, now all you have to do is click on the
Cloud Code here, and then press the slash command. And now, if you just try trade, all of these
different commands will be available for you. Okay? So, that's for the paid community. You have
access to this one command uh installation process. And then also, for the ones that are not part of
the paid community, if you just installed or if you just downloaded that folder with zip file, all
you have to do is just unzip it and click on skills. You're going to have all of these skills
available. You're going to copy all of that, come back to your folder that you just created, and
paste it there in your dot cloud file or dot cloud file. And that's it. You'll be able to Same
thing, open up a new uh Cloud Code instance, and you will have access to all of these uh um skills
there. Okay? So, now let's go ahead and take a look at this and run this on another stock. So, I'm
just going to go ahead and now do slash trade, right? So, now you have all of these options
available for you. So, this time I'm going to actually go ahead and do trade quick. So, let's do
trade quick this time. So, I'm going to just scroll here and press uh trade {dash} quick. And then,
uh there's another company called Rivian, which is a competitor of Tesla. Actually, that's not how
you That's not their ticket. It's RIVN. They're a competitor of our Tesla. They're another big uh
electric car company. So, I'm going to press enter. So, now it's going to go ahead and actually do a
quick analysis for the Rivian, which is again a electric car company. So, as you can see, now it's
going to do the web research to find out all of the different details about the stock pricing today,
the market cap, and the high and low and everything else. So, let's go ahead and let this thing
finish. Now, while this is loading, of course, for those of you who are not part of the paid
community, if you're interested in learning how to build these tools, not just this This is of
course just for personal reasons, right? You just want to run trade. But if you're interested in
building uh Cloud Code projects that you can sell to different businesses and make money with it,
that's where you can join the community. We have different projects. So, at GEO, we just started our
agency that we're servicing uh GEO clients for with Cloud Code. So, we're going to share all of the
different results that we get with customers. And then also, AI reputation builder, everything. This
is designed for you to sell this to businesses and make money with it because of course Cloud Code
is fun to learn, but if you don't make real projects that solve real business pain points, nobody's
going to pay you, right? So, all of that is inside the classroom section. And of course, if you're
interested in starting your AI agency, I have a step-by-step guide, like day-to-day accountability
guide, on how to start your AI agency. So, check out the link in the description. Uh join us. We'd
love to have you there. All right. So, let's go ahead and back take a look at it and see what's
going on. All right. This looks like it finished. It only took like 20-30 seconds, but it gives you
like a gives you like a quick snapshot. You know, it says Rivian Technologies uh AI trading analyst,
right? 20 Yeah, that's April 8th. Gives you the price, the market cap, the 52-week low, uh volume.
It gives you the signal, hold, bullish factors, bearish factors, key levels, thesis, one night EV
maker at a fundamental flexion, first gross profit, R2 launch imminent, but technical downtrend and
cash burn warrant patience. Wait for a break above $15.72 or pull back to 13 support. Again, by the
way, and that's why I have the disclaimer here. This is just for your research. Of course, this is
not any kind of trading advice. Uh that's why I mentioned that a lot of people on YouTube who are
building like these trading bots and telling you, "Oh, do this, do that." That's not a good idea
because for most people, you have to understand that trading is a very complex project. That's why a
lot of times people just buy um the S&P 500 or something like that. But for those of you This is for
people who are doing day trading or interested in learning how to do those things or just in
general, if they want to do trading, this gives you that tool. This tool gives you that research arm
that otherwise you would uh spend months or weeks doing this manually, right? So, that's what this
is for. So, take a look at it. Again, play around with the other ones. All of the uh different
skills that are here are are very useful. Um and of course, the more, you know, you run this on
different stocks, the more you will understand how amazing this tool is and how much research it
provides actually. Again, Cloud Code is absolutely incredible. And the fact that we have access to
things like this is amazing. Again, these are things that before would be only accessible to the
hedge fund managers, to different companies, but now we can build tools like this, which is
absolutely mind-boggling. Anyways, hopefully you found that helpful. Make sure you like, subscribe
because I've got a lot more content that I'm planning to build with Cloud Code, especially these
kind of tools teams that are in the research space that I think is going to be super useful that you
don't want to miss. Thanks for watching, and I'll see you on the next one.
