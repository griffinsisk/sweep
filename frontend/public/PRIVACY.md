# Privacy

Sweep is a tool for cleaning up your own Gmail. This is what it does with your data.

**What it accesses.** With your permission, Sweep reads message metadata (sender, subject, date, size, labels) and moves or deletes messages you choose. It reads your Google storage quota to show how much space you have.

**What it stores.** Nothing. Your Google access and refresh tokens are encrypted and stored in a cookie in your browser. The server holds nothing between requests. Signing out deletes the cookie.

**What it sends to third parties.** When you ask for suggestions, Sweep sends sender domains, message counts, and up to three subject lines per sender to Anthropic's Claude API to classify them. It never sends message bodies, recipients, or your email address.

**What it never does.** Read message content. Send email. Act without a click from you. Sell or share your data.

**Revoking access.** Visit https://myaccount.google.com/permissions and remove Sweep at any time.
