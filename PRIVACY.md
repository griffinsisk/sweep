# Privacy

Sweep is a tool for cleaning up your own Gmail. This is what it does with your data.

**What it accesses.** With your permission, Sweep reads message metadata (sender, subject, date, size, labels) and moves or deletes messages you choose. It reads your Google storage quota to show how much space you have.

**Where it runs.** On your own computer. There is no hosted service. The only server involved is the one Sweep starts on your machine, and it talks directly to Google.

**What it stores.** Nothing on any server. Your browser keeps a small per-account history in its own local storage: when each session started, Google's storage figure at that moment, and Sweep's estimate of what you deleted. It never leaves your machine; clearing site data removes it. Your Google access and refresh tokens are encrypted and stored in a cookie in your browser. The local server holds nothing between requests, and the encryption key is regenerated each time it starts. Signing out deletes the cookie.

**What it sends to third parties.** When you ask for suggestions, Sweep sends sender domains, message counts, and up to three subject lines per sender to Anthropic's Claude API to classify them. It never sends message bodies, recipients, or your email address.

**Unsubscribing.** When you press Unsubscribe, Sweep does only what that sender's own mail headers offered. For a sender that supports one-click unsubscribe (RFC 8058), Sweep posts the standard request to the sender's https address, with no cookies and nothing from your account. For a sender that only offers a mailto address, Sweep can send one short message from your Gmail account to that address, and only after you tick "Also send unsubscribe emails from my account". That box is off by default and resets every time the page loads. Sweep reports a request as "requested", not "unsubscribed", because it can only know that the sender accepted it. The date of each request is kept in your browser's local storage, alongside the history above.

**What it never does.** Read message content. Send email, other than the unsubscribe messages you turned on. Act without a click from you. Sell or share your data.

**Revoking access.** Visit https://myaccount.google.com/permissions and remove Sweep at any time.
