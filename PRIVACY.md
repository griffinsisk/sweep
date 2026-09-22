# Privacy

Sweep is a tool for cleaning up your own Gmail. This is what it does with your data.

**What it accesses.** With your permission, Sweep reads message metadata (sender, subject, date, size, labels) and moves or deletes messages you choose. It reads your Google storage quota to show how much space you have.

**Where it runs.** On your own computer. There is no hosted service. The only server involved is the one Sweep starts on your machine, and it talks directly to Google.

**What it stores.** Nothing on any server. Your browser keeps a small per-account history in its own local storage: when each session started, Google's storage figure at that moment, and Sweep's estimate of what you deleted. It never leaves your machine; clearing site data removes it. Your Google access and refresh tokens are encrypted and stored in a cookie in your browser. The local server holds nothing between requests, and the encryption key is regenerated each time it starts. Signing out deletes the cookie.

**What it sends to third parties.** Nothing. The only service Sweep talks to is Google.

**What it never does.** Read message content. Send email. Act without a click from you. Sell or share your data.

**Revoking access.** Visit https://myaccount.google.com/permissions and remove Sweep at any time.
