# I Tested the Viral Claude Code Trading Strategy — It's WAY Worse Than I Thought

- video: https://youtu.be/Bo8oYgy4qyE
- lang: en
- source: automatic_captions (сырой ASR, черновик)

---

In my last video, I called out a viral AI trading strategy. The response was absolutely massive. We
are talking eight comments. But I just couldn't leave those eight people hanging. So, I spent my
whole evenings on this while working full-time. He never shared the actual code, which is perfectly
fine. He just showed the prompts he used. So, I had to reconstruct the entire thing from scratch in
Python just from that. And yes, I used AI to help me build it and speed up the process, which is
perfectly fine. I went through everything, every parameter combination I could think of. And I just
couldn't get to his numbers. I was starting to seriously doubt these results were actually a real
output of this model. And then I found it. One line right there on his own dashboard. And it
explains everything. Just as a quick recap. This is what he's claiming. 233% return, 99 trades,
sharp off 1.46, 200% alpha versus buy and hold. Built in 10 minutes with Claude. I called
BS/overfitting in my last video, but I couldn't prove it until now. So, I rebuilt the entire model
in Python. Same HMM, same seven states, same confirmation signals, same leverage, same date window.
I ran it over and over, and I just couldn't get anywhere near 233%. Not even close. I went through
every single line of logic, checked the entry conditions, checked the exit conditions, tried
different parameter combinations, And I kept thinking, what the f am I missing? How is he getting
233% on an asset that returned 34% in the same period? And then I looked closer at his dashboard.
Not the numbers, the small print. Right there in the subtitle of his own dashboard, it says grid
optimized leveraged alpha version 2.0. Most people scroll right past that. I almost did, too. But if
you know what grid optimization actually means, that one line explains the entire 233%. Here is what
grid optimization is in plain English. You build a model, then you brute force every single
combination of parameters through it. Every setting, every confirmation threshold, every cool down
period, every hold time, hundreds of combinations. And then you just pick the one that produced the
best historical results. Take a screenshot, make a video, sell excess. I'm just kidding. That is
obviously not a trading strategy. That's a parameter search. And it's completely meaningless for
future trading because you already knew the answers before you started. So I ran my own grid grid
optimization. Same model, same data, 240 parameter combinations. And look what I found. I got there,
or at least close to there, not because I'm smart, not because my model is better, just because I
searched through enough combinations until the back test looked good. Exactly what he did. The
difference is I am telling you that's what I did. And this is the thing about AI that nobody talks
about in this crazy hype. When you don't actually know what you're doing, and clearly that's the
case here, AI doesn't save you. It just automates the mistake faster. Claude didn't build a hedge
fund strategy. It builds a grid search wrapper with a pretty dashboard. And then someone put a price
tag on it. The evidence was right there in the title, grid optimized, in plain sight, on the
dashboard he filmed himself using. Now, if there is enough interest, I am happy to go through the
full model and show you how to actually build this properly, out of sample testing, real transaction
costs, walk forward validation, everything you need to know if this actually works or not. But let's
be honest, I'm not going to spend my evenings on that for 1K or 2K views. Everything I've done in
these two videos, the date window reverse engineering, the dumb benchmark test, the full HMM
reconstruction, the grid optimization code, is available in the channel membership. It's basically
just code access, no course, no promises, just the actual work so you can run it yourself. But I'm
not selling you a strategy. I have never, and I never will. It's 15 bucks a month, and it directly
helps me keep doing this. That's it. No more, no less. If this kind of content is useful to you,
that's how you support it. Thanks a lot, and I'm looking forward to seeing you in the upcoming
videos. Cheers. Bye-bye.
