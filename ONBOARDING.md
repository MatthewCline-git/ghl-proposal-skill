# Onboarding: instructions for the AI assistant

You are setting up the **ghl-proposal** skill for the person you're talking to. It turns call notes into a draft proposal in their GoHighLevel (GHL) account. Setup takes about 10 minutes.

There are two editions in the repo, and you pick one by what is **already on their machine**, never by asking them to install something:
- **Scripted edition** (`ghl-proposal`): Python scripts do the retries, duplicate guard and verification the same way every time, keep a run log, and can push failure alerts. Use it **if Python 3 is already installed**.
- **Lite edition** (`ghl-proposal-lite`): no scripts; Claude calls GHL directly with `curl` following the playbook in `SKILL.md`. Use it **if Python 3 is not installed**. Don't make them install Python.

**How to behave**
- Work one step at a time. Keep messages short. Say exactly where to click, then wait for the user to confirm before moving on.
- Do the technical parts yourself (files, commands). Only ask the user to do what needs their hands: clicking in GHL, and pasting the token into a file.
- **Never ask the user to paste the GHL token into this chat.** They put it in a file (step 4).
- Tell them what you're about to do before you do it. If a command fails, read the error, fix it, and explain in one sentence.
- If you can't run shell commands or write files in this session (a plain chat), stop and tell the user: "Open Claude Code (the Code tab in the Claude desktop app, or a terminal), start a session, and paste the setup message again."

Start by saying: "I'll set up your proposal skill in about 10 minutes. It has four parts: install it, connect it to your GoHighLevel account, build one proposal template, and restart the app."

---

## Step 1: Install

1. **Pick the edition.** Run `python3 --version` (on Windows also try `python --version`).
   - It prints `Python 3.x`: use the **scripted** edition.
   - "command not found", or on Windows a message or a Microsoft Store window: use the **lite** edition.
   - **macOS trap:** `/usr/bin/python3` can be a stub that pops up a "command line developer tools" install dialog instead of running. If `command -v python3` is `/usr/bin/python3` and `xcode-select -p` fails, treat Python as **not installed**, don't trigger the dialog, and use lite.
   - For lite, also check `curl --version` works (built into macOS, Linux and Windows 10+).
   Tell them which one you chose and why in one sentence.
2. Get the code. If `git --version` works:
   `git clone https://github.com/MatthewCline-git/ghl-proposal-skill.git ~/ghl-proposal-skill`
   (if that folder exists, run `git -C ~/ghl-proposal-skill pull` instead). Without git: download `https://github.com/MatthewCline-git/ghl-proposal-skill/archive/refs/heads/main.zip` and unzip it to `~/ghl-proposal-skill`.
3. Install the chosen edition by **copying** (not linking, so it works on Windows too) into a folder named `ghl-proposal`. Scripted: source folder `ghl-proposal`; lite: source folder `ghl-proposal-lite`.
   `mkdir -p ~/.claude/skills && cp -R ~/ghl-proposal-skill/<source folder> ~/.claude/skills/ghl-proposal`
   On Windows (PowerShell): `Copy-Item -Recurse $HOME\ghl-proposal-skill\<source folder> $HOME\.claude\skills\ghl-proposal`.
   If `~/.claude/skills/ghl-proposal` already exists, ask before overwriting, and never delete an existing `.env` inside it.
4. Confirm `~/.claude/skills/ghl-proposal/SKILL.md` exists. Tell them: "Installed. Next I'll connect it to GoHighLevel."

## Step 2: Find their sub-account (the location ID)

Ask exactly this:

> Log in to GoHighLevel and open the **sub-account** you want proposals to go into: the actual business account, not the agency dashboard. Then copy the full web address from your browser's address bar and paste it here.

The address looks like `https://app.gohighlevel.com/v2/location/AbC123xyz/launchpad`. The location ID is the piece right after `/location/` (here `AbC123xyz`), up to the next `/`.

- If the address has no `/location/`, they're in the agency view. Tell them to switch into a sub-account with the account switcher at the top left, then paste the address again.
- If the domain isn't `app.gohighlevel.com` (a white-label domain), keep that host and later add `GHL_APP_URL=https://<their host>` to the `.env`.

Then build this link, **open it for them** (macOS: `open "<url>"`; Windows: `start "" "<url>"`; Linux: `xdg-open "<url>"`), and also print it:

`https://app.gohighlevel.com/v2/location/<LOCATION_ID>/settings/private-integrations`

## Step 3: Create the token (their hands)

Tell them, in this order:

1. "On the page that just opened, click **Create new Integration** (top right)."
2. "Name it `Claude proposals`."
3. "Under scopes, tick these (use the search box in the list): **contacts.readonly, contacts.write, locations.readonly, users.readonly, locations/customFields.readonly, locations/customFields.write**, everything for **Documents & Contracts** (both the documents and the templates entries, view and send/edit), and, only if you also want estimates, **invoices/estimate.readonly** and **invoices/estimate.write**."
4. "Click **Create**. GHL shows the token **once**. Click copy, and keep the page open until we've saved it."

If they can't find a scope by that name, tell them to pick the closest ones under Contacts, Custom Fields, Locations, Users and Documents & Contracts. If they get stuck, ticking every scope works; the token stays on their own computer. The check in step 4 will name anything missing.

## Step 4: Save the token in a file (not in this chat)

1. In `~/.claude/skills/ghl-proposal/`, copy `.env.example` to `.env`.
2. Write their location ID from step 2 after `GHL_LOCATION_ID=`. Leave `GHL_TOKEN=` empty.
3. Open the file in their editor so they can paste: macOS `open -t ~/.claude/skills/ghl-proposal/.env`; Windows `notepad %USERPROFILE%\.claude\skills\ghl-proposal\.env`.
4. Tell them: "Paste the token right after `GHL_TOKEN=` (no spaces or quotes), save the file, and tell me when it's saved. I won't look at the token."
5. When they say saved, run the **setup check**. Scripted: `python3 scripts/check_setup.py` from the skill folder. Lite: read the **Setup check** section of `~/.claude/skills/ghl-proposal/SKILL.md` and carry it out yourself (load the `.env`, run those reads with `curl`); either way report ✓ or ✗ per item with the fix for each ✗, and never print the token. Fix what you can; for a missing scope, send them back to the integration page to tick it (the token can be edited, no need to recreate). At this stage only **proposal template** should be ✗; that's step 5. The check also creates the five proposal fields in their GHL, which is expected.

## Step 5: Build the proposal template (their hands, one time)

GHL doesn't let software create templates, so this is manual, and it's the part that most often goes wrong. Go slowly.

1. Open the template text for them: macOS `open ~/.claude/skills/ghl-proposal/template/proposal-template.html` (Windows: `start "" "%USERPROFILE%\.claude\skills\ghl-proposal\template\proposal-template.html"`). It opens in their browser. Tell them: "Press Cmd+A (Ctrl+A on Windows), then Cmd+C."
2. "In GoHighLevel, go to **Payments → Documents & Contracts → Templates**, click **New**, and choose the blank proposal option. Click into the page and paste. You'll see text like `{{contact.proposal_scope}}`. That's intentional; leave it exactly as is."
3. "Rename the template to exactly **Proposal** (name at the top of the editor)."
4. "Put **Acceptance** and the signature on their own **second page**. Signature fields sit at a fixed spot, and real proposals are longer than the placeholder text, so on page one the text can run over the signature."
5. "Under Acceptance, add a **Signature** field for the client (assigned to the signer). Add a date field if you like."
6. "Save."

Then run the setup check again. Everything should be ✓, including the template named `Proposal`. If it isn't found, they mis-typed the name or haven't saved.

## Step 6: How they get paid (optional defaults, one minute)

**Prices are per proposal**: the skill asks for the total each time and never stores or guesses one. The only things worth saving are the standard terms. Ask in **one message**:

> Two quick things so I can save defaults (skip either; I'll ask on your first proposal instead): 1) How do you usually get paid, and is there anything you put on every proposal (revisions, cancellation, fees at cost)? 2) How many days should a proposal stay valid? (14 if you're not sure.)

Write the answers into `~/.claude/skills/ghl-proposal/defaults.json` (`terms`: a list of short sentences; `valid_days`), read them back, and get a yes. Don't propose terms for them.

## Step 7: Restart the app (required)

Tell them clearly:

> **Quit the app completely and reopen it.** On Mac press **Cmd+Q** (closing the window isn't enough). On Windows, quit it from the system tray. Skills are only picked up when the app starts, so the skill won't exist until you do this. When it's back, start a **new chat**.

Because the app restarts, this conversation may be gone. So **before they quit**, write them a test message to paste into the new chat, built from **their own services**:

> /ghl-proposal Test proposal for <made-up person>, <made-up company>, <name>@<something>.example.com. Notes: <2-3 sentences describing a made-up client situation that their kind of work would solve>. Deliverables: <2-3 things a business like theirs would deliver>. Total: <an obviously fake round number>. Terms: <their terms from step 6, or a plain one>. Dry run first, then create the draft.

The email must end in `.example.com` so nothing can ever be sent to a real person. The message carries everything the skill needs so it won't have to ask questions. Tell them to paste it after the restart. If typing `/` doesn't show `ghl-proposal`, check that `~/.claude/skills/ghl-proposal/SKILL.md` exists and restart once more.

## Step 8: First test (in the new chat, with the skill loaded)

The skill shows the exact proposal text with its light edits (the total and terms exactly as given), then creates a **draft** document. It always tells them to open it in GHL before sending. Have them open **Payments → Documents & Contracts → Documents**, open the draft, and check: the client's name and company are filled in, the intro, scope and total read correctly, the layout is clean, and the signature sits on page two. Nothing is sent to anyone; documents are always drafts.

Test data (the made-up contact and draft) can be deleted in GHL afterwards.

## Step 9: Optional extras

Mention once and only if they want it. Scripted edition: failure alerts (`ALERT_WEBHOOK_URL`, a Slack incoming webhook, or `ALERT_EMAIL` plus `RESEND_API_KEY`, in the `.env`; otherwise alerts only go to `runs/alerts.log`) and scheduling `python3 scripts/watchdog.py` to catch runs that hang; see `RUNBOOK.md`. Lite edition: failures are reported in the chat and each run is one line in `runs.log`; if they later want alerts and a watchdog, they can install Python and switch to the scripted edition.

Finish by telling them how to use it day to day: "After a call, say `/ghl-proposal`, then the client's name, company, email and your call notes."
