# Proposal template: one-time setup in GHL

GHL's API can send a proposal template but can't create one, so you build it once by hand.
The skill looks for a template named exactly **Proposal**.

1. Open `proposal-template.html` in your browser, press Cmd/Ctrl+A, then Cmd/Ctrl+C.
2. In GHL: **Payments → Documents & Contracts → Templates → New**. Choose the blank proposal option and paste into the editor. Keep every `{{...}}` exactly as pasted.
3. Rename the template to **Proposal** (name field at the top of the editor).
4. Put **Acceptance** and the signature on their **own second page**. Signature fields sit at a fixed spot on the page, and merged text is longer than the placeholders, so on page one it can run over the signature.
5. Under Acceptance add a **Signature** field for the client/signer. Optionally add a date field.
6. Save. Then ask Claude to run the setup check; it should report the template `Proposal` found.

Merge fields the skill fills (contact custom fields, created automatically): `proposal_intro`, `proposal_scope`, `proposal_total`, `proposal_terms`, `proposal_valid_through`. The company and name fields and `{{location.name}}` come from GHL.
