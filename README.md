# tozi-pins

Pinterest pins for Tozi Packaging (pinterest.com/tozipackaging/), published through RSS auto-publish.

- `pins.py` draws each pin from the product's own photo and the product page's own words, and links it to the product page.
- A GitHub Action (`.github/workflows/daily.yml`) adds 3 pins a day and updates `feeds/<board>.xml`.
- GitHub Pages serves the feeds and images at https://userepicc.github.io/tozi-pins/.
- On Pinterest: Settings > Bulk create Pins > Auto-publish, one feed per board.

Fonts: Lora and Inter (SIL Open Font License, see `fonts/`). Task: T-026 in agentic-ai-hub.
