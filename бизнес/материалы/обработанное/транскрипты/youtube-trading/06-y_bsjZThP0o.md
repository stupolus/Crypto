# How To Actually Build a Trading Bot With Claude Code (Fully Automated)

- video: https://youtu.be/y_bsjZThP0o
- lang: en
- source: automatic_captions (сырой ASR, черновик)

---

In today's video, I'm going to show you how you can build a fully automated trading bot from scratch
using Cloud Code. So, it will first detect the type of market we're in, adjust your portfolio
allocations automatically, and even places real trades for you. We're not going to be building some
basic indicator bot that just buys when RSI crosses above 30 like what you would typically see on
TradingView. Instead, we're going to be building an actual system that first connects to a real
brokerage so that you can automatically place trades. Second, it'll manage your risks with circuit
breakers. And then finally, it can even adapt to changing market conditions automatically. And we're
going to be doing this without writing any of the code ourselves. So, if you've seen my previous
videos, I go over the concepts around using hidden Markov models and walk-forward backtesting
engines. Today, we're going to be taking those same concepts one step further. So, we're going to
grab that same exact math, but now connect it to a real broker so that we can have a bot actually
manage our portfolio for us. So, make sure to stay until the end of the video since I'll be covering
how to build this exact system step-by-step, even if you have no technical knowledge or you've never
coded before. And just as a disclaimer, I'm not a financial advisor and this is not financial
advice. I'm not guaranteeing any profits inside this video. All I'm doing is showing you the
concepts on how to build a systemic trading framework to help you become a more disciplined trader.
Trading involves real risk and it's up to you to manage, validate, and extensively test your own
strategies. So, here's what our automatic trading bot dashboard looks like as a finished product and
what building by the end of this video. So, up top we can first see the detected regime, which is
currently neutral. This basically tells us how volatile the market currently is and how we should
classify it. And then below, we even have a confidence score. And then to the right of this, we have
our portfolio value as well as our buying power. Now again, this is connected directly to a
brokerage, in our case Alpaca. So, these are the numbers that are currently inside our trading
account. To the right of this, we have the number of regimes that the current system is categorizing
the market into. And right now the market's closed, so we don't have any active positions. Then
below this, we just have simple price actions with regime overlays. Below this, we have volumes,
confidence over times, distributions. And this way you'll be able to see how this actually
translates to your trading strategy. And then below all of this, importantly, we have the signal
feed, which actually shows all of the historical trades that this automatic trading bot has placed.
So this way it'll tell you the allocation from your portfolio size, as well as entry prices, stops,
and P&L in real time. Then to the left of this, we also have risk controls. And this basically shows
our circuit breakers, drawdown limits, and leverage statuses, so that we manage our risk properly
and obviously don't blow up our account. Then finally, these are all of the regimes that our trading
system is currently characterizing the market into. So we have a crash, bear, neutral, bull, and
euphoria. And then obviously, depending on the regime that the market is currently in, our
allocation is going to change, and our strategies are going to change as well. So the way you can
think about this is that depending on the regime that our trading system is currently detecting the
market as, our strategies are going to be different. The amount of capital that we're going to
allocate per trade is going to be different as well. And again, everything here was built by Claude
Code, right? Which is a coding agent. All you'll need to do is prompt properly, understand the
structure of your code base, and I'll be going over this from start to finish, so that you can have
your own version of this trading dashboard and automatic trading bot for use yourself. Now, before
you start building out this automatic trading bot, let me first explain the system and all the
things we need to make step-by-step to ensure that we have a comprehensive system that covers
everything we would theoretically need. So you can think of this entire system as being made up of
five components. We'll have the brain, allocation, safety, brokerage, and then finally the dashboard
that displays all of our information. So to start off, right, every system needs a competent brain
at the center that basically makes decisions. But, in our case, our brain is going to be hidden
Markov models. Now, I've went over this in previous videos, but you can think of this exact system
as essentially looking at the market historically as well as with live data and then classifying
what type of market we're in. So, by looking at things like price action and volume, it's able to
classify the market. So, it'll tell us if the market is in a crash, if it's currently a bear market,
if it's in a bull market, or just full-blown euphoria where everything just goes up. And now,
depending on the type of market that we're in, the strategies are going to differ, right? So, inside
our automatic trading bot, we want to make sure this is as dynamic as possible. And the way this bot
is going to trade inside a bear market or choppy market is going to be very different from a
trending bull market. So, before we ever make any trading decisions, before we ever layer any
strategies of our own or yours on top, we need to know first what type of market it is. So, this is
basically just how we should be looking at the market before ever adding any strategies. And that
goes into my next point, which is step two on allocation. So, you can think of this allocation layer
as being directly influenced by the brain. So, what this means is that, depending on, you know, the
volatility regime, whether in a crash, bear, neutral, bull, or euphoria, it's going to change the
amount we're invested in our portfolio. So, typically, in calm markets, you would have a larger
amount of capital allocated. And then, in more turbulent markets, you would typically reduce your
exposure to protect your capital. And we're going to use those same exact concepts inside our
automatic trading bot as well. Now, for our third component, we have the safety net. Essentially
shuts everything down if certain levels are hit. So, basically, if you hit like a max drawdown in a
day, if your strategies aren't working like they're supposed to, it's able to essentially call it
quits, uh shut off the entire system. This way, you won't continually lose money day by day, week by
week, or even during that same exact day as well. Just depending on how you structure these circuit
breakers, which I'll show you later on in the video. And one thing to know is that these work
independently of our AI model. So, whatever strategies, uh hidden Markov models, systems we have,
these safety nets are going to be hardcoded in a sense, so that even if our strategies are
technically built correctly, they should work theoretically, these safety nets are completely
independent of that. And this is huge, obviously, for automated trading bots because you don't ever
want to just turn on a bot and have it continually lose money, right? You'll have to essentially
call it quits at some point and think about how to revisit your strategy and how to actually build a
better system moving forward. And then now for step four, we have the broker. So, this is where you
can choose the brokerage that you want to connect your system to. Two main options I would typically
consider. The first is Alpaca. This is generally free, depending on how much volume you're trading.
Obviously, if you get into like millions of dollars of volume trading, you're going to have fees on
top of this. Uh but once you do get to that certain level, then I would probably change to IBKR.
This is going to be paid. So, this is where our code can place real orders directly through the
system to Alpaca. If you sign in to Alpaca, which I'll show you later on in the video as well,
you'll be able to see all your trades, performance, and how much money you have in your account.
Then finally, to tie everything together, we have the dashboard and this is where you can see
everything in real time. So, now that we understand how this automatic trading bot is going to be
structured, let's go ahead and build out every single one of these components one by one. So, this
way you'll be able to see like from step one till the end, we're going to be following the same
exact timeline. Uh we're going to be able to test independently. So, we're going to be test that the
HTML models work. We're going to test that the allocation and sizing works. We're going to test that
the safety net works as well. We're going to test our strategies and backtest those. We're going to
be testing our brokerage connection, so we can first see that the trades are actually getting placed
through Alpaca. And then finally, the dashboard will essentially tie everything together. Now,
before we start building the project, I basically inputted every single step along the way inside
this master document. If you want to get access to this, you can go ahead and click the link in the
description for my school community. I'll go ahead and showcase everything in a bit more detail so
that you can customize these to your own strategies. I'll also show them in the video, too. So, this
way if you want to just pause at certain parts of the video to see how you would change up the
prompt, you can go ahead and do so. But, just to give you a broad overview, what we're first going
to do is create the project scaffolding. So, this is kind of like the shell of the entire system.
Then, below this we have the regime detection engine. So, this is going to be the brain that we
talked about. We have the volatility-based allocation strategies. These are where you're going to
input your custom strategies based on how you trade and what you're actually trading. Below this, we
have walk-forward backtesting and validation to make sure that your strategy does work properly. And
then finally, we have a risk management layer that ensures that our system doesn't blow up our
account. We have proper, you know, circuit breakers in place, things like that. And then finally,
once we've validated that everything works and is safe to a degree, we're able to connect it to
Alpaca, which is a brokerage we're going to be using. Below this, we can make sure that the main
loop and orchestration works. So, this is where we're going to extensively test that we're able to
send trades to Alpaca. It's receiving all our data. And then finally, we're going to monitor, have
alerts, and have a dashboard that showcases all of the trades we've taken, historical performance,
how our system's currently working, and just a way to visually see our system in real time.
Obviously, everyone trades very differently, but the idea here is to have a very a general base case
that almost anyone can use. Uh you just want to go ahead and change the strategies, change the
tickers you're working with, but obviously keep the core logic here the same. Now that we've gone
over the structure, let's go ahead and start building out this actual auto trading bot project. So,
the first thing you'll need to do is go ahead and download an IDE where you can use Cloud Code. This
is where your code base is going to live, and in our case, we're going to be using Visual Studio
Code since it's pretty much the simplest way to go go and get started. So, all you'll need to do is
download Visual Studio Code and then open up a blank folder inside your computer. Next, what you
want to do is add Cloud Code as an extension. Search Cloud Code. You should see it pop up as the
very first extension. It's called Cloud Code for VS Code. This is the easiest way to go ahead and
get started. So, now once you've installed the Cloud Code extension, you should be able to see it on
this right-hand side here. This is where we're going to be able to chat with Cloud Code, which again
is going to help us make all the projects. We're going to need to give it very useful instructions
one step at a time based on the diagram I showed you previously. Next, what we're going to be doing
is something called project scaffolding. So, inside the section, we're going to be creating just a
project structure. So, no actual logic yet, but we're just going to be creating a Python project
called Regime Trader with the following structure. And again, there's nothing yet inside these
files. This structure is just what's going to tell Cloud Code how our files are going to look.
First, we're going to have settings, credentials, HMM engine. So, this is going to be the brain.
Then, we're going to have regime strategies. So, based on the regime that we're in, it's going to
have volume-based allocation strategies. Then, we're going to have a risk manager that's going to
handle position sizing, leverage, drawdown limits. This is basically the API wrapper that allows us
to connect to Alpaca, which is our brokerage. Then, we're going to have an order executor. This is
what's going to allow us to actually place trades to the Alpaca API. So, as the name suggests, we're
able to place trades, modify trades, and even cancel trades. We're also able to track our open
positions because once we're connected to Alpaca, we can see positions that are currently open. We
have market data, which is real-time and historical. We have feature engineering, which is technical
indicators, structured logging, the dashboard. This is where our dashboard's going to live. Alerts,
so email, webhook alerts for critical events. This is if you ever want to connect your email. Below
this, we have the backtester. We have performance. So, here we're able to calculate the sharp
ratios, drawdowns, regime breakdowns, benchmarks. This is everything you saw inside the main
dashboard that I showcased initially, uh which basically gives us our strategy as a whole, how it
relates to the overall market. Then below those, we have all of the tests that we're going to be
running. This is the verify like no look ahead biases, testing out strategies, risks, order, etc.
And we're going to be doing extensive testing each step of the way because again, this is going to
be an automated trading bot and we have to make sure that it's being validated at every step. And
then finally, we just have the main file, requirements, and then the ENV file is where we're going
to be storing our credentials. If we're going to be using the Alpaca API, this is where we're going
to store the API keys that allow us to connect to our live account. Below this, we need a
requirements file that basically has everything we're going to be using inside this trading
framework. Then finally, we want to create a settings file that has all the parameters. Now, this is
where you're essentially going to be changing the tickers that you want to focus on. Then below
this, we have more specific parameters for the hidden Markov models, the strategies that we're going
to be using depending on the regimes, risks, back tests, and monitoring. Again, we don't want to
implement any logic yet. So now, let's go ahead and run this. So after waiting like 5 minutes or so,
we can see the project skeleton is complete. We have 31 files across eight directories. The first is
going to have settings with all the parameters. So this is the broker we're going to use, the HMMs,
strategies, risks, back tests, and monitoring. Next, we have the core. So these are the core
parameters that we're going to be using inside the framework, where we're getting data from,
monitoring, back testing. And if we go over here to the left, we can even see all of these files are
created inside regime trader. And again, this is pretty much standardized no matter what strategy
you have. Cloud code does work best when it has the structure all built out before we start diving
deep into the weeds. Now that we finished project scaffolding, the next step is to create the brain
of our entire trading bot. So again, like I mentioned, these aren't going to predict prices. They're
going to predict the type of environment that the current market is in, whether it's calm, volatile,
whether we're in a bear market. So, by detecting these different types of environments, we're able
to reduce our exposure, change our strategies. So, in this next prompt, we can see that we're going
to be implementing the HMMs, and this is going to be a volatility classifier. It's going to tell us
the type of environment, like I mentioned. Below this, we want to do different types of tests to see
how many regimes there are. So, inside my example from the beginning of the video, you saw that we
had five regimes, right? But, the five wasn't hardcoded. That's actually something we found out
through testing. So, the idea here is that this model is going to test, you know, three through
seven regimes, and then this is automatically going to pick the best number of regimes. So, instead
of us guessing how many there should be, we're just going to have this math here dictate that. Then,
below this, we're just going to sort the regimes by mean return. This is going to help us label the
regimes. So, with three, it's only bear, neutral, bull. With four, it's crash, bear, bull, euphoria.
Five would be crash, bear, neutral, bull, euphoria. Then, below this, we have a bunch of functions
that, again, you can copy and paste or just get it directly from my community. But, you can pause
and see any of the very specific calculations we're going to be running inside these functions. And
then, below this, this is how we're going to actually train the HMMs with around two years of daily
data. Below this is the regime detection. Now, one important thing to know, especially if you want
to run this yourself, is that the default predict function inside the HMM library is processes the
entire sequence of data, but that generally creates look-ahead bias. So, what we do is make a slight
tweak here to not use the model predict function. Instead, what we're going to be using is the
forward algorithm only. So, make sure to include this inside your prompt, and this is just to ensure
that there's no look-ahead bias when you're developing these models and strategies. So, here you can
see the function. If I slowly scroll down, you can see the mandatory tests. And then, below this, we
have the regime stability filter, as well as additional methods for predicting, getting regimes,
detecting regimes, and then finally, how we classify the states, and then log regime changes as a
warning. This is just for our information. And then with the way we build this out here, Quad has a
stability filter inside this engine. What this means is that a certain regime has to persist for at
least three consecutive bars before the system acts on it. So if it's like flickering between bull,
bear, bull, bear, it's not actually going to do anything if it flickers more than four times in the
past 20 bars. That is what causes uncertainty. So we're going to log those changes as kind of like a
warning sign. So this way it does reduce your position sizes ultimately because it is more volatile
and uncertain as to what regime the market is currently in. All we're building here is again just
the brain, right? That detects the type of market before you apply any other allocation strategies.
So here after like 10 minutes or so, since we had such a robust prompt, it basically implemented
everything we asked for inside these two files, so the feature engineering as well as the HMM
engine, which is again going to be the main brain. It's also passing and validating the test that we
had it complete after completing these sections to ensure that first of all the HMMs fit the
validations, uh they're doing predictions correctly, and then there's no look-ahead bias as well.
Next, what we're going to want to do is our allocation strategies, and this is how the bot is going
to tell us how to size positions based on the regime that we're in. Here we can see that the HMMs
excel at detecting volatile environments, and then based on the environments, we would essentially
have fully invested portfolios, stay invested if the trend's intact, or just reduce your allocations
completely. So below we have a fairly simple strategy that obviously you would want to change if
you're going to customize this to your own framework. But what I have here is three main
distinctions. The first is that when volatility is low, to be fully invested at 95% of your
portfolio with 1.25x leverage. And then when the volatility's medium, we can stay invested if the
trend is intact. But again, this is the part that you're going to customize. So maybe you would want
to be more aggressive in a low volume market. Maybe you'd want to have a different filter for medium
volumes. And then obviously you'd want to add your own specific strategies on top as well. So the
idea here is that you just want to replace this entire section with your own personal strategies
depending on your own risk tolerances. And then below this we have the volatility rank mapping
strategy orchestrator. We have confidence and uncertainty. So again, a lot of these are hardcoded
based on what I found works. There's also rebalancing. This is how we're going to implement
everything. So we have a base case, we have the low volume bull strategy, strategy orchestrator,
signal data class. And then below this we just have some aliases and labels. This is going to be the
part where you spend the most amount of time in. And before we even connect to a brokerage, we want
to prove and make sure that our strategy does work. So the idea is to tweak this a bit. What we're
going to do is first send over this prompt just to have our base strategies layered in. And then
once we add in backtesting, we can go back and forth with Claude Code to really optimize a strategy
that works for your specific use case and your asset class or ticker that you're trading. And also
we can see that all 32 tests pass. Again, we want to make sure that we have tests on every single
phase of our build out. Below this we can see our different strategies, which again is a very
general strategy that you would obviously change based on how you trade and based on what tickers
you're trading as well. We just have different strategies on the type of regime. Below this we have
the key components. Next, what we're going to want to do is build out the walk forward backtesting
engine. And this is what's going to allow us to test out that strategy we just implemented to see if
it works on blind data historically and also how it's potentially going to do in the future. So what
we're going to be doing here is splitting data into rolling windows. And this allows us to do an
allocation based walk forward backtest. This isn't like a traditional backtest because typically you
would have all the data, find the perfect settings in hindsight, and then have it pretend that it
predicted the future. With this we're able to run blind test historically to see how it would have
actually done without having all the data beforehand. And I'm just expanding out this prompt just so
you can read it a bit more clearly. If you want to pause in certain parts of the video, you can and
take in some of these concepts and then basically tailor it to whatever strategy you're running. But
the logic should remain largely the same. So the idea is that we want to build out this walk-forward
optimization engine. So we'll have rolling windows and the in-sample windows will be 252 trading
days. Out of sample will be around 6 months for evaluations. So you can see how we're running this
allocation-based backtest. Below this we have the math as well as realistic simulations. This is
just for slippage. And then finally we have performance metrics. So we want to calculate the total
return, the sharp ratio, max drawdowns, win rates, total trades, things like that just be able to
quantify how it actually performed. Then we'll want to make sure that this is separated out by
regime as well as confidence bucketed so we know if it's high confidence trades that are
outperforming low confidence trades and vice versa. Then we're going to want to compare the backtest
to three main benchmarks. The first is buy and hold. Obviously, if you were to take a ticker, you
would see how our strategy performed simply by actively trading it versus just buying and holding
for that entire historical window. We would also want to compare against the 200-day SMA trend
following. This is one of the most common systemic strategies and then below this we just have a
random entry and random allocation changes with same risk rules. And then if you want to go even
more in-depth, we have stress tests that just basically inject random crash events. So this is just
to bake in very specific like 10 to 15% in a day drops. So on this step, obviously you're going to
need to go back and forth with your own strategy. Make sure that you're backtesting it properly.
This is honestly going to take the longest amount of time at least for you because once you do have
a strategy dialed in, you're probably going to need a lot of iterations before you find something
that really does pass all these stress tests as well as the benchmark comparisons. After you go back
and forth with Quad Code, you should end up with first a backtester file that will show all of the
windows that it's currently testing your strategy on as well as the other components. And then below
this, you should have a performance file that shows all the metrics. So, your core metrics, trade
stats, regime tables, confidence buckets, things of that sort. So, you can see how your strategy
performed. And obviously, you would want to go back to the drawing board, change up your strategy,
things of that sort if your performance hasn't been too stellar historically, at least. And then
below this, we should have stress test. This just shows how your performance handled under extreme
stress in the market. And all of this information should be tested and should pass based on our
prompt. Now, after we verify and validate the backtesting results, what we need to do is build a
layer that guarantees in the worst case of trading, it's going to stop our system. And this is what
I talked about earlier, which is the risk management layer. This is probably the most important
system in your entire trading framework, more important than the HMMs, even. Because a mediocre
strategy with a great risk management layer only loses money a little bit. If you had a great
strategy, but with bad risk management, you could basically blow up your account. So, basically, you
can think of this risk management as having the absolute veto power over everything. We'll have
circuit breakers basically built in here. So, if it's down 2% in a single day, all sizes are cut in
half. If it's down over 3%, close everything. If it's down 5% in a week, then you want to half your
sizes. If it's down 10% from peak, so you have a 10% drawdown, the bot just stops completely and
writes a block file that you have to manually delete. These are here just to make sure that you
don't blow up your account, right? You can have a great strategy, but a few bad days can basically
trigger some of these. And if you don't have these in place, things can spiral out of control fairly
quickly. And this last one here that I have highlighted is pretty deliberate. If it's down 10%, if
you see how it's going to write this file, what that means is that you have to go look at what
happened. It's going to go ahead and write a file for you, so you understand what went wrong in the
strategy if it was really down 10% from peak. Uh you go inside, you understand why this occurred,
and then you have to consciously and manually turn it back on. So, this forces you to go into the
system, see what happened, and you need to manually delete this file to resume your strategy. And
this is just to make sure that you trust the strategy moving forward because this can be a pretty
significant blow in your account. Now, below this we have position level risk. This is basically
sizing. So, every trade risks a maximum 1% of your portfolio. Now, you can obviously change this if
you want a bit more risky. Then below this, we have leverage, which again you would want to change
to your own tolerances, what you're comfortable with. Then below this, we have order validation and
then correlation checks. So, before opening a new position, the bot checks if it's correlated with
any existing positions. This is just a way to make sure that we're not entering the same type of
trades. But the idea here is that I want to give you the core logic that should be able to be
applied generally, no matter what kind of trader you are, but obviously change some of these
settings if you want to. So, here you can see that the risk manager has been built with all the
thresholds. You can see the circuit breakers and all of their trigger levels. And then below this,
we have, you know, the minimum size, risk-based sizing, position limits, things of that sort. So,
everything we talked about. You can go ahead into the file if you want to validate, but we have test
again on every single step to make sure that everything is passing. So, now if you were to look at
the timeline of our automatic trading bot, we've built out the brain that's going to classify the
market. Uh this is everything that drives decisions. We've built out the allocation and strategies.
These are how much of the portfolio to invest in and how to invest. And we just finished out the
safety as well. So, this way we have circuit breakers in case losses hit a certain level. So, with
this, we basically have the core engine done. What we next need to do is connect this to a
brokerage, and in our case Alpaca. And then with the brokerage, we're able to send trades directly
from the system here to the broker. The broker can automatically place trades for you without you
lifting a finger, hence making it fully automatic. So now, let's go ahead and sell back and I'll
show you how to create your free account and connect everything inside Cloud Code. So what you'll
first want to do is head over to alpaca.markets and this is the API for stocks, options, and crypto
trading. This way you'll be able to automatically place trades from our system for all these asset
classes, just not futures. Go ahead and click sign up and what you want to use is the trading API.
Now once you've created your account, it'll automatically place you in a paper trading account. Now
what I would recommend is to start with this trading account first, connect your system to it,
monitor it for at least a month to make sure that everything is working and that your strategy does
seem to potentially have an edge. And only once you've done extensive testing and even live market
testing, would I then click open live account on that same strategy. Again, make sure that the
trades are being sent properly, but we can do this in a paper account. This way we can validate that
our strategy works in the meantime, make sure that trades are being sent and then because it's a
paper trading account, we can do as much testing as you want back and forth to really hone in our
strategies. So inside your account, what you'll want to do is scroll all the way down and you should
have a section called API keys. It'll go ahead and give you a secret key as well as your API key. So
all you need to do is copy these three things. The first is this endpoint, this will be your base
URL. Then copy this, this will be your API key and then copy this, this will be your secret key. So
these are the three things that'll let you connect from Cloud Code's trading system that it's
building for you directly to your actual account here at Alpaca. And then obviously, this goes
without saying, never share these keys with anybody. I'm going to regenerate these after this video
as well. This is just to make sure that no one has access to your funds, especially if it's a live
account. This is something that we're not going to have Cloud do for us and the reason for that is
because we don't want to share sensitive information like API keys directly to their chat. This is
something we're going to have to do ourselves and it'll be super simple. We've already built out the
core structure, so nothing much to do. So if you go over to get ignore, you can see that the .env
files are going to be ignored. This means that if you publish this, your .env files won't ever be
leaked. They're going to be private. And you can even see an example of what this looks like. So,
Claude code from our very first prompt has already created the structure for us. Alpaca API key,
this is just that API key I told you to copy. Secret key is that secret key I told you to copy. And
then paper, this can be true. You'll also need the base URL as well, but since that's not
confidential, we can just type it into the chat here. What's important is that we never share the
API key or the secret key to Claude code. We want to just type this in ourselves. So, all you want
to do is very simple. Go ahead and create a new file, and then this will be our .env file. Uh paste
it here, and then what you want to do is fill in your API key, fill in your secret key, and then
keep this to be true. So, after that, I can show you the prompt now for the Alpaca broker
integration. What we first want to do is create this file that's going to allow us to connect. We
already have the base URL here, so this is the URL that you copied from that very first step inside
Alpaca. It's going to be pretty much the same. What you'll see here is that our credentials are in
our .env files. So, again, never hardcoded. Then below this, we have all the other parameters.
Broker order executor, this just lets us actually submit orders, cancel orders, modify stops, things
like that. We also have a position tracker, so we're able to see all the orders that we currently
have, as well as market data. Now, this prompt isn't going to be something custom like those
allocation strategies. It's pretty much going to be the same for everyone. So, if you want to take a
screenshot of this section of the video, feel free to do so. So, now after we paste this in, it's
able to read our .env files and then help connect us to the Alpaca API directly. Now, after we
submitted everything, we just want to do a quick check to make sure that the API is connected.
Confirm API is connected. The base URL, again, is that base URL we copied with the secret and the
API keys. And then what we want to do is place a trade for Nvidia as a test, and we should see this
trade come through to our Alpaca dashboard as well. So, go Go and click enter here. And we can even
see here as it's loading, the API is connected, the account is active with around 100,000 in paper
equity. Market's currently closed cuz it's the weekend, but with paper trading you can still have
orders queue. So, if they're going to place a test buy for Nvidia, we should be able to see it
inside our Alpaca dashboard. And over here on the Alpaca dashboard, again, this is our paper
account. If we scroll down, we can see asset was Nvidia. It was just a market buy. Uh we can even
see the date was literally right now, so it was submitted on April 4th at 4:47. So, this basically
confirms to us that the system is basically connected to our Alpaca brokerage here. Now that we have
all the components of our system built out with the brain, HMMs, we have the strategies,
allocations, we also have the actual brokerage connected as well as safety, back test, things of
that sort. We just want to connect everything together with phase seven here. So, basically, when we
start up the system, we want to load the configuration, connect to Alpaca, verify the account, check
market hours to see if it's open or closed, train the HMMs. We would then want to initialize risk
manager, initialize position tracker, start all the data feeds, things of that sort. So, this is
basically the bridge that ties everything we've built thus far. And then below this, we have the
main loop for each bar close. Default is 5-minute bars. Then below this, we have shutdowns in case
that needs to be used, error handling just to ensure that if there's any issues with the Alpaca API,
if the server is down on their end, or if there's any HMM errors on our end, uh data feed drops,
things of that sort. This is just sure that our engine keeps running smoothly no matter what happens
either on our end or their end. So, now let's go ahead and copy and paste this into Cloud Code, and
this will essentially glue everything. And while we wait for this to run, basically, uh this is the
last step before we create the dashboard to visually show everything, but technically, once this is
wired, we don't really need a dashboard. That's only if you want to visually see what's happening in
your system, which I highly recommend. But, if you don't, you can stop at this step and just
continually test out your strategies, uh watch the orders go in on the Alpaca dashboard. Awesome.
Now, here we can see that all 134 tests pass, basically every single test that connects every
component of our trading system. And as a final step, all we need to do is make this a bit more
visual so we can see everything that's happening from the back end onto our UI and make any changes
as necessary. So, this is what the monitoring alerts and dashboard prompt looks like. We just want
to make sure that all of our trades are being monitored and logged properly. Uh we're going to use
this monitoring for different positions, uh recent signals. So, after pasting in that prompt, if you
wanted a visual dashboard, you can just say build a Streamlit dashboard as the UI. So, after a
while, we can see that all 134 tests pass. All our monitoring and logging works for the trades. And
then as a final step, we just asked it to install the dependencies needed to run the Streamlit
dashboard. And awesome, let's go ahead and paste this into our browser. Now, here we can see our
final dashboard. So, obviously, it's still on a paper account. We have our portfolio values. Right
now, the market's closed, so it's not going to show any positions active. But, the idea here is to
always, you know, test rigorously. Make sure this works on a paper account, whichever strategy
you're running. You can see all the trades coming in, whether they're performing or not. Below this,
we have the regime detection. So, this is what tells us the volatility of the market. Right now,
it's saying we're in a bear regime with 100% confidence. We also have risk statuses in case we ever
use any leverage or if we're hitting any circuit breakers. Below this, we also have portfolios. So,
obviously, right now, we just created the system, so there's no open positions. But, the idea is to
constantly monitor this dashboard day in and day out as the system finds more trades for you, logs
them based on your strategy, and you're able to see the performance. So, that's the entire system. A
few important things to note. First is to obviously paper trade for at least a month. You want to
make sure to watch every decision your bot's making for you, understand why it rebalanced your
portfolio, why it stayed put, when the risk manager overruled something. Again, recall back all
those different rules we had set. Next, the allocation numbers here are swappable, and so you can
always change up your strategy, how much of your portfolio is going to be allocated in certain
regimes. These can always change depending on testing. It's basically paper trade, review every
single rebalance, run back test across different tickers, periods, iterate on your allocation
parameters, on your strategies, and then use Cloud Code to continually improve. So, the beauty of
this system is that it actually created documentation for every single file we built. So, if you
were to hop into VS Code, if you go over to the read me file, you can see an overview of the entire
system. So, with this entire system, Cloud Code basically knows your code base in and out. If you
ever need to make any changes, it's able to add them on the fly. Um it's able to review its work.
So, this is going to take a lot of back and forth, but the potentials here are basically limitless.
And like I mentioned earlier in the video, if you want more detailed guides and the complete prompt
here, you can click the link in the description for my community. I also have custom one-to-one
projects if you want to build out a custom strategy or system that you're using. And if you found
this video helpful, make sure to like, comment, and hit subscribe as I go over everything regarding
using AI for trading. I think tools like Cloud Code have really opened up the possibility for retail
traders to really quantify the strategies. They're able to use systems like these that were
previously never really accessible to the average Joe, but now almost anyone can hop into Cloud
Code, build out these super complex systems, test out their strategies, and just help them become a
more disciplined and profitable trader.
