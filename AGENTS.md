# Repository guidance

This is an independent collection of original Memoh bot presets, not a Memoh fork.
Keep persona prose in Chinese and developer documentation concise. Use Python 3.10+
standard library only. Do not embed credentials, provider IDs, user data, copied
community prompts, lyrics, or scripts. Approved identifying avatar thumbnails live
in assets/avatars with their separate source/rights records in catalog/avatars.json;
do not add other official artwork. Cite research sources and
distinguish documented facts from original roleplay scenarios.

Match the pinned upstream contract in docs/research/upstream-contract.json. Run
`python3 -m unittest discover -s tests -v` and `python3 -m memoh_templates validate`
before committing, then repeat on a clean checkout. Heavy work belongs on vultr-sg.
Never test on an existing user's bot; use a disposable bot and remove it afterward.
