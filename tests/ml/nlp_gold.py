"""Synthetic notes with hand-written expected mentions. A REGRESSION set, not validation evidence (I48).

The notes were written by the same team that wrote the lexicon, so a perfect score here says nothing about real
notes. Every name, number and place is made up.
"""
P, A, U = "present", "absent", "uncertain"

GOLD = [
    ("Child has swelling of both feet.", {("oedema", P)}),
    ("No oedema seen.", {("oedema", A)}),
    ("Oedema absent.", {("oedema", A)}),
    ("pitting edema on both legs", {("oedema", P)}),
    ("? oedema of the feet", {("oedema", U)}),
    ("possible malaria, no diarrhoea", {("malaria", U), ("diarrhoea", A)}),
    ("Had convulsions at home this morning.", {("convulsions", P)}),
    ("denies convulsions", {("convulsions", A)}),
    ("no fever, no cough, convulsions yesterday", {("convulsions", P)}),
    ("No oedema but convulsions present", {("oedema", A), ("convulsions", P)}),
    ("Child is lethargic and not eating well.", {("lethargy", P), ("poor_appetite", P)}),
    ("not alert, floppy", {("lethargy", P)}),
    ("Unable to breastfeed since last night", {("unable_to_drink", P)}),
    ("can't drink, vomiting", {("unable_to_drink", P)}),
    ("Eating well. No diarrhoea.", {("good_appetite", P), ("diarrhoea", A)}),
    ("good appetite, passed appetite test", {("good_appetite", P)}),
    ("Mother says poor appetite for 3 days", {("poor_appetite", P)}),
    ("watery stools x4, refusing food", {("diarrhoea", P), ("poor_appetite", P)}),
    ("unconcious on arrival", {("unconsciousness", P)}),          # one letter missing: still found
    ("Unresponsive to voice", {("unconsciousness", P)}),
    ("malaria negative", {("malaria", A)}),
    ("no sign of oedema, diarrhea ruled out", {("oedema", A), ("diarrhoea", A)}),
    ("Edema? Not sure", {("oedema", U)}),
    ("MUAC 11.5 cm, weight 8.2 kg, age 14 months.", set()),
    ("", set()),
    ("Routine visit. Child playful and alert.", set()),
    ("seizures overnight; denies diarrhoea", {("convulsions", P), ("diarrhoea", A)}),
    ("CHILD HAS SWOLLEN FEET AND IS DROWSY", {("oedema", P), ("lethargy", P)}),
    ("not eating well but no oedema", {("poor_appetite", P), ("oedema", A)}),
    ("appetite good, no convulsions", {("good_appetite", P), ("convulsions", A)}),
]
