"""Generate `script.pdf`, the demo running order.

    python -m pip install reportlab
    python tools/make_script_pdf.py

reportlab is the ONE dependency this project has that is not in
`requirements.txt`, on purpose: it is needed to rebuild the PDF and by nothing
else. `script.pdf` is committed, so nobody has to install anything to read it.

The content lives in SECTIONS below. Editing the running order means editing
this file and re-running it, rather than editing a binary nobody can diff.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "script.pdf"

TITLE = "Simple Bank: live demo script"
SUBTITLE = ("Running `python console.py --mongo` beside the MongoDB Atlas "
            "Data Explorer")

# (heading, [ (kind, text), ... ])
# kind: "p" paragraph, "do" what you type, "look" what to open in Atlas,
#       "say" what to say out loud, "note" a caution
SECTIONS = [
    ("Before you start", [
        ("p", "Two windows, side by side. The terminal on the left, a browser on "
              "the right."),
        ("do", "python console.py --mongo --reset"),
        ("p", "<b>--reset</b> empties the demo database so you begin from nothing, "
              "which makes the first record you create visibly the first record. "
              "Leave it off to keep what is already there."),
        ("look", "cloud.mongodb.com &rarr; Cluster0 &rarr; Browse Collections "
                 "&rarr; the database named in the console banner "
                 "(<b>your MONGODB_DB + _console</b>)"),
        ("note", "Atlas does not refresh by itself. Every time you want to show a "
                 "change, press its refresh icon. An empty-looking collection is "
                 "almost always a stale page, not a failed write."),
        ("note", "Set BANK_SECRET in .env first, or tokens stop working whenever "
                 "you restart the server. Not needed for the console, but it will "
                 "bite you if you also demo the REST API."),
        ("say", "“This is the same service layer the REST API calls. Nothing "
                "here can succeed that the API would refuse.”"),
    ]),

    ("1 — Register a user", [
        ("p", "Choose <b>1</b>. It prompts one field at a time. Let the room pick "
              "the name."),
        ("do", "Name / Email / Password (not hidden) / User or Admin (1 or 2)"),
        ("look", "<b>users</b> &rarr; the _id the console just printed"),
        ("say", "“The password is not in this document. There is a "
                "password_hash field — PBKDF2, salted, 600,000 rounds. The "
                "plaintext never reaches the database, and never reaches any "
                "response.”"),
        ("look", "<b>counters</b> &rarr; _id: \"users\""),
        ("say", "“That is our AUTO_INCREMENT. Mongo would give us an "
                "ObjectId; the brief asks for integer ids, so we allocate them "
                "atomically on the server with find_one_and_update and $inc.”"),
        ("note", "Register a second user with the SAME email to show the refusal. "
                 "It is stopped by a unique index on users.email, not by Python — "
                 "so it holds even if two servers try at once."),
    ]),

    ("3 — Open an account", [
        ("p", "Choose <b>3</b>. Pick Checking or Savings, then an opening balance. "
              "Type it in dollars, e.g. 250.00."),
        ("say", "“Watch the conversion line: 250.00 becomes 25000 cents. "
                "Money is an integer number of cents everywhere — never a float, "
                "never a Decimal. That is the single design decision I would "
                "defend hardest.”"),
        ("note", "The console prints the ACCOUNT NUMBER in a box. That number "
                 "is the _id of the accounts document, and every later prompt "
                 "offers it as the default — press ENTER to take it."),
        ("look", "<b>accounts</b> &rarr; the new _id. Point at the balance field."),
        ("say", "“balance is 25000, an Int64. Not 250.00 as a Double. A float "
                "cannot hold 0.10 exactly and the error compounds across a "
                "ledger.”"),
        ("look", "<b>transactions</b> &rarr; the _id printed alongside"),
        ("say", "“The opening balance was not assigned, it was posted. Every "
                "balance in this system equals the sum of its ledger entries, and "
                "that is true from the first second the account exists.”"),
    ]),

    ("4 — Deposit (and the double-click)", [
        ("p", "Choose <b>4</b>. Press ENTER for the account number, type an "
              "amount, then press ENTER again to take the suggested reference "
              "id (<b>ref-001</b>)."),
        ("say", "“A reference id is a label the caller invents for one "
                "transaction — a real client would send a UUID. The bank "
                "stores it and refuses anything that repeats it.”"),
        ("look", "<b>transactions</b> &rarr; new _id, and <b>accounts</b> &rarr; "
                 "the balance field has changed"),
        ("say", "“Two documents changed together: the ledger entry and the "
                "balance. Never one without the other.”"),
        ("p", "<b>Now do it again</b> — same account, same amount — "
              "but this time type <b>ref-001</b> back in instead of "
              "pressing ENTER. The console lists the ids already used, so it is "
              "on screen in front of you."),
        ("say", "“Refused. That is the double-clicked submit button. The "
                "guarantee is a unique index on client_txn_id, so it holds across "
                "processes — a set in Python memory would only protect one "
                "server.”"),
        ("look", "Refresh <b>transactions</b> and count: no new document. The "
                 "refusal wrote nothing."),
        ("note", "This is the most convincing thing in the demo. A database with "
                 "nothing new in it, after an action that looked like it should "
                 "have added something."),
    ]),

    ("5 — Withdraw more than the balance", [
        ("p", "Choose <b>5</b> and ask for more than the account holds."),
        ("say", "“InsufficientFunds. Over HTTP that is a 409. The check and "
                "the write happen inside one transaction, so two simultaneous "
                "withdrawals cannot both pass it.”"),
        ("look", "<b>accounts</b> &rarr; the balance is unchanged. Nothing was "
                 "written."),
    ]),

    ("2 — Log in as someone else", [
        ("p", "Register a second user (<b>1</b> again), then use <b>2</b> to move "
              "between them."),
        ("say", "“Logging in writes nothing — the console says so. It reads "
                "the stored hash and compares. Even an unknown email is checked "
                "against a decoy hash, so the response takes the same time either "
                "way and does not leak which addresses are registered.”"),
        ("p", "Now, as the second user, try <b>7</b> on the FIRST user’s "
              "account number — type it over the default rather than "
              "pressing ENTER. The prompt accepts any number on purpose."),
        ("say", "“AccountNotFound — and note it says <i>no account with "
                "id 1</i>, the same thing you get for an id that was never "
                "issued. Over HTTP that is a 404, not a 403: saying ‘you are "
                "not allowed to see this’ would confirm the account "
                "exists.”"),
        ("p", "Try <b>4</b> on the same account number for the same effect on a "
              "write."),
        ("look", "Nothing changed in <b>transactions</b> or <b>accounts</b>."),
    ]),

    ("6 — Transfer between accounts", [
        ("p", "Open an account for the second user first, then choose <b>6</b>."),
        ("look", "<b>transactions</b> — TWO new documents, TRANSFER_OUT and "
                 "TRANSFER_IN. <b>accounts</b> — both balances moved."),
        ("say", "“Four documents, one MongoDB transaction. Atlas can never "
                "show you a state where the money has left one account and not "
                "arrived at the other.”"),
        ("say", "“This is why we are on Atlas rather than a local mongod. "
                "Multi-document transactions need a replica set. A standalone "
                "server accepts the same code and gives no atomicity, "
                "silently.”"),
    ]),

    ("8 — Admin actions", [
        ("p", "Register an ADMIN (option <b>1</b>, then choose 2 at the role "
              "prompt), then choose <b>8</b>."),
        ("p", "<b>Freeze an account.</b> Try a reason under ten characters first "
              "— it is refused."),
        ("look", "<b>accounts</b> &rarr; status is FROZEN. <b>audit_log</b> &rarr; "
                 "the _id printed — who did it, and the reason."),
        ("p", "Switch back to that customer (<b>2</b>) and try to deposit."),
        ("say", "“Refused while frozen.”"),
        ("p", "<b>Then post an adjustment.</b>"),
        ("look", "<b>transactions</b> &rarr; the new entry carries "
                 "<b>adjusted_by</b> and <b>reason</b>; an ordinary deposit has "
                 "neither."),
        ("say", "“There is no set_balance method anywhere in this codebase. "
                "It is the easiest admin feature to write and the wrong one: a "
                "balance that moves without a ledger entry breaks the invariant "
                "permanently, and afterwards you cannot tell which of the two is "
                "right.”"),
        ("p", "Finish with <b>8 &rarr; Reconcile every account</b>."),
        ("say", "“Every balance still equals the sum of its ledger. Integers, "
                "so that comparison is exact and needs no tolerance.”"),
    ]),

    ("7 and 9 — Reads, and the closing proof", [
        ("p", "<b>7</b> shows history and reconciliation for one account. It "
              "writes nothing, and says so."),
        ("p", "<b>9</b> opens a second, independent connection and reads "
              "everything back."),
        ("say", "“None of those numbers came from this program’s objects. "
                "They were read out of Atlas by a connection that has never seen "
                "them.”"),
        ("p", "Strongest close: quit the console entirely, start it again "
              "<b>without --reset</b>, and press <b>9</b>."),
        ("say", "“Different process. Same data. That is the thing an "
                "in-memory store can never show you.”"),
    ]),

    ("If something goes wrong", [
        ("note", "<b>The collection looks empty.</b> Press refresh in Atlas. It "
                 "does not poll."),
        ("note", "<b>Nothing connects.</b> Run <b>python tools/check_mongo.py</b> "
                 "— seven checks, each naming what to change. Usually the IP "
                 "access list."),
        ("note", "<b>‘email already registered’ for an email that is not "
                 "there.</b> The id counter is behind the data. Reload with "
                 "<b>python server.py --reset</b>."),
        ("note", "<b>A refusal you did not plan.</b> Keep going and read it out. "
                 "Every refusal in this system is a rule doing its job, and they "
                 "are the most interesting thing on the screen."),
    ]),

    ("Also available", [
        ("p", "<b>?</b> at the console menu — every term on screen, "
              "with the reason behind it: the five collections, _id, reference "
              "id, cents, and what each refusal proves. Read it before you "
              "present; open it live if a question lands that you would rather "
              "answer from the screen than from memory."),
        ("p", "<b>python demo.py --step</b> — the scripted walkthrough, paused "
              "between sections. Use it if you would rather not type."),
        ("p", "<b>python simulate.py</b> — continuous traffic against Atlas, "
              "about one action every two seconds. Good for leaving running in "
              "the background while you talk."),
        ("p", "<b>python server.py</b> then Postman — the same rules as real "
              "HTTP status codes, using the committed collection."),
    ]),
]


def build():
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer,
        )
    except ImportError:
        print("This needs reportlab, which is not in requirements.txt because")
        print("nothing else uses it:")
        print("    python -m pip install reportlab")
        return 1

    ink = colors.HexColor("#1a1a1a")
    muted = colors.HexColor("#5a5a5a")
    accent = colors.HexColor("#0b5c3f")
    warn = colors.HexColor("#8a4b00")
    rule_grey = colors.HexColor("#d6d6d6")

    base = getSampleStyleSheet()["BodyText"]
    styles = {
        "title": ParagraphStyle("title", parent=base, fontName="Helvetica-Bold",
                                fontSize=20, leading=24, textColor=ink,
                                spaceAfter=2),
        "subtitle": ParagraphStyle("subtitle", parent=base, fontName="Helvetica",
                                   fontSize=10.5, leading=14, textColor=muted,
                                   spaceAfter=14),
        "h": ParagraphStyle("h", parent=base, fontName="Helvetica-Bold",
                            fontSize=13, leading=16, textColor=ink,
                            spaceBefore=13, spaceAfter=5),
        "p": ParagraphStyle("p", parent=base, fontName="Helvetica", fontSize=10,
                            leading=14.5, textColor=ink, alignment=TA_LEFT,
                            spaceAfter=5),
        "do": ParagraphStyle("do", parent=base, fontName="Courier-Bold",
                             fontSize=9.5, leading=13.5, textColor=ink,
                             leftIndent=8, spaceBefore=2, spaceAfter=6,
                             backColor=colors.HexColor("#f2f2f0"),
                             borderPadding=5),
        "look": ParagraphStyle("look", parent=base, fontName="Helvetica",
                               fontSize=10, leading=14, textColor=accent,
                               leftIndent=10, spaceAfter=5),
        "say": ParagraphStyle("say", parent=base, fontName="Helvetica-Oblique",
                              fontSize=10, leading=14, textColor=ink,
                              leftIndent=10, spaceAfter=5),
        "note": ParagraphStyle("note", parent=base, fontName="Helvetica",
                               fontSize=9.5, leading=13.5, textColor=warn,
                               leftIndent=10, spaceAfter=5),
    }
    # A word in front of each line saying what kind of line it is, so the page
    # can be read at a glance from a lectern rather than word by word.
    prefix = {
        "look": "<b>LOOK:</b> ",
        "say": "<b>SAY:</b> ",
        "note": "<b>!</b> ",
        "do": "",
        "p": "",
    }

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(rule_grey)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 16 * mm, A4[0] - 18 * mm, 16 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(muted)
        canvas.drawString(18 * mm, 11 * mm, "Simple Bank - live demo script")
        canvas.drawRightString(A4[0] - 18 * mm, 11 * mm, f"page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(str(OUT), pagesize=A4,
                          leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=16 * mm, bottomMargin=22 * mm,
                          title=TITLE, author="Simple Bank Application G2")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=decorate)])

    flow = [Paragraph(TITLE, styles["title"]),
            Paragraph(SUBTITLE, styles["subtitle"])]

    for heading, items in SECTIONS:
        block = [Paragraph(heading, styles["h"])]
        for kind, text in items:
            block.append(Paragraph(prefix.get(kind, "") + text, styles[kind]))
        # Keep a section on one page where it fits, so nobody turns a page
        # mid-step with an audience watching.
        flow.append(KeepTogether(block))
        flow.append(Spacer(1, 1))

    doc.build(flow)
    print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(build())
