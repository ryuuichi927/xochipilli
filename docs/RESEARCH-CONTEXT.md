# Research context

I study everyday listening: whether a stretch of listening gets a person where they meant to
go, and what it costs them when it doesn't. This file is about the one place that work reached
into Xochipilli, and the places I kept it out.

None of it is research. There are no participants, and the only person it records is me.

## The reason list

When a take is wrong I record why. The reasons are fixed (`app/taste.py`):

```
emotion · world · camera · style · episode · other
```

![The Unmatch sheet with the episode reason selected](media/unmatch.png)

Five of them are craft complaints. The mood is off, the setting is wrong, the camera is doing
something I didn't ask for. The sixth is a different kind of failure, and the sheet says so in
the one line it gets: wrong kind of engagement, even if the picture is fine. A take can be
well made and still fail to do what that stretch of music was for. The note field asks for
that rather than for a rating.

> e.g. wanted calm, got pushy energy

In the research this is the ordinary case, not an edge one. Someone puts music on to settle
and comes out wound up. Without that habit of mind the list would have stopped at five, and
this failure would have gone into `emotion` or `other`, where it reads as taste rather than as
a purpose that was missed. It carries its own count (`episode_mismatch_count`), and `function`
and `purpose` normalize onto it so that synonyms don't split it.

`episode` is only the internal name. On screen it reads Engagement, 体験の働き, 体验作用. The
research word would mean nothing to someone directing a shot. The English label is also not
the involvement construct from my own work, which describes a standing feature of a person
rather than one discarded take. Those two words landing near each other is an accident of
English.

## What I kept out

Segments here are intervals I pin in a song, often only a few seconds long. Stamping a
listening purpose onto each one would have been easy to build and would have produced
something chartable.

An episode is a whole occasion. A reason for playing something, a situation, and a person in
whatever state they were in when they pressed play. A pinned interval of a waveform is none of
that, and cutting a song into segments does not hand me a sequence of episodes. So the idea
enters at the single point where I do make a judgment about purpose, which is when I throw a
take away.

Valence and arousal are a different case. They are dimensions rather than occasions, so they
can sit on a segment without the category error. They stay optional, and they get sampled when
I reject something (`affect_samples`). On screen they are **Feel**, one slider running from
Still to Moving and the other from Low to Bright. See [CRAFT.md](CRAFT.md) for the layer they
belong to.

## What the store is for

Rejections feed the next prompt, not a dataset. Repeated signals merge softly into the STYLE
and NEGATIVE fields (`taste.merge_prompt_fields`, on by default, `apply_taste` per project to
turn it off). The point is that I stop retyping the same correction.

It stays thin: counts, recent entries, rejected keywords, hints. It lives in
`<data>/user/taste.json`, where `<data>` is `~/Documents/Xochipilli` unless
`XOCHIPILLI_DATA` says otherwise. It sits outside the repository and the application never
uploads it.

## Limits

One user and no controls, so anything in that file describes my own afternoons. Whether other
people would reliably tell `episode` apart from `emotion` while annotating their own
rejections is an empirical question, and this tool doesn't answer it. The borrowing also runs
one way. The category made the software better; it tells me nothing new about listening.
