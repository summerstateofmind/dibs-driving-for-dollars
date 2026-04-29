# iOS Shortcut: "Log This House"

One-tap or "Hey Siri, log this house" capture while driving/walking.

## What it does

1. Grabs your current GPS location
2. Reverse geocodes to a street address
3. Opens a pre-filled text to your D4D number
4. You add condition notes (optional) and hit send

## Setup (takes 2 minutes)

1. Open **Shortcuts** app on iPhone
2. Tap **+** to create new shortcut
3. Name it **"Log This House"**

### Add these actions in order:

**Action 1: Get Current Location**
- Search "location" → add "Get Current Location"
- Accuracy: Best

**Action 2: Get Details of Location**
- Search "Get Details" → add "Get Details of Location"
- Get: **Street** from Current Location
- (This gives you just the street address like "4823 32nd Ave NE")

**Action 3: Get Details of Location** (again, for city)
- Add another "Get Details of Location"
- Get: **City** from Current Location

**Action 4: Text**
- Search "text" → add "Text" (the variable block, not Send Message)
- Set it to: `[Street] [City]` (tap the variables from steps 2 and 3)

**Action 5: Send Message**
- Search "Send Message" → add it
- To: **(833) 853-8107**
- Message: tap the Text variable from step 4
- Toggle OFF "Show When Run" if you want it fully automatic (no preview)
  - Or leave ON if you want to add notes before sending

### Optional: Add to Home Screen
- Tap the shortcut name → Add to Home Screen
- Pick an icon (house emoji works)

### Siri activation
- Just say **"Hey Siri, log this house"** — it matches the shortcut name

## Tips

- To add condition notes while hands-free: leave "Show When Run" ON, then dictate notes after the address in the message preview
- The tool will parse the address and notes separately via AI
- Works with CarPlay — say "Hey Siri, log this house" while driving
