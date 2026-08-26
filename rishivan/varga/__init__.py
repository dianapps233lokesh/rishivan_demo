"""Which divisional charts may speak, and when they must be withheld.

Blueprint §7: *"Do not use every Varga merely because it exists. Each Varga must
have a documented purpose, calculation method and evidence hierarchy."* And:
*"The engine should not present false precision."*

    confidence.py  how much of a recorded birth time is actually known
    policy.py      purpose, method, evidence tier and confidence floor per varga
    select.py      which vargas a question gets, and what was withheld and why

The withholding is the product. "D60 needs a birth time to the minute; yours is
recorded to the hour, so I have not used it" is a sentence no astrology app
says, and it cannot be said by a pipeline that silently drops the varga.
"""
