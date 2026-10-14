Bug report: a healthy backup API key gets benched after a rate limit.

Setup: two API keys for the same provider. The primary key comes from ~/.hermes/.env; a second, backup key was added to Hermes' credential pool. The two keys belong to different upstream accounts.

What happens: the primary key hits its monthly usage limit and the provider returns 429. Hermes correctly marks it exhausted and switches the session to the backup key. A turn or two later, though, both keys show as exhausted ("no available entries (all exhausted or empty)"), even though only the primary key ever hit a limit. The backup key is benched for the full cooldown and the session stops working. To the user it looks like an auth failure, but it is a misattribution: the failure of one key is being recorded against the other.

Expected: a 429 is always attributed to the key that actually sent the failing request; a healthy key that has not failed is never marked exhausted, and the session keeps working on the backup key.

Find the root cause in this repository and fix it, including any sibling code paths that contribute to the misattribution. Add or update tests that cover the fix. Do not break existing tests.

Run tests from the repository root with:

    {TEST_CMD}

When you are done, reply with a short summary of the root cause and the list of files you changed.
