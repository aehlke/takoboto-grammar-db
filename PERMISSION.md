# Scraping permission and operator instructions

**[Alex Ehlke](https://github.com/aehlke), the author of this scraper, received
permission from Takoboto's owner to run it against Takoboto's grammar section.**
That permission applies to the author's preservation work on the JGram-derived
grammar collection, including the public contributions associated with it.
It is not a blanket authorization for other people to scrape the website.

**Before running this scraper against Takoboto, contact
[Takoboto](https://takoboto.jp/) and obtain permission for your own crawl.**
Use the contact information on their website, describe your intended scope and
schedule, and follow the conditions they provide. GitHub forks, the source-code
license, and the Creative Commons data license do not transfer the author's
site-access permission to you.

When authorized, keep requests within the grammar dataset. Start with a small
test, retain the conservative sequential batches and pauses, obey robots.txt
and server Retry-After, and stop on access denials or rate limits. Do not use
this scraper to collect dictionary data, profiles or other site sections.
The `--contact` option identifies you in requests; it does not contact Takoboto
to ask for permission.

The optional JGram supplement uses Internet Archive's Wayback Machine. Follow
[the archive request rules](docs/archive.md) and any applicable Archive.org
restrictions; Takoboto's permission does not authorize bypassing those rules.

Downloading the released database or building exports from the committed JSON
records requires no requests to Takoboto or Archive.org. Data redistribution
follows [CC BY-SA 2.0](LICENSE-DATA.md), with [source and contributor credits](ATTRIBUTION.md).
This project is independently maintained and does not claim official endorsement.
