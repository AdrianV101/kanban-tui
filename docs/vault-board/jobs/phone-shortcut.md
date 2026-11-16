# Phone capture Shortcut

Build an iOS Shortcut named Capture. It appends one line to `00-Inbox/Capture.md` in the vault. The morning sweep turns each line into a draft card.

## Build it

Add two actions.

1. **Ask for Input**. Type: Text. Prompt: "Capture".
2. **Open URLs**, with this URL:

```
obsidian://new?vault=<vault>&file=00-Inbox%2FCapture&content=<input>&append=true&spacing=newline&silent=true
```

Replace `<vault>` with the vault name as Obsidian shows it. If it has spaces, URL-encode them (`%20`).

Replace `<input>` with the text `- ` followed by the Ask for Input result, URL-encoded:

1. Add a **Text** action before Open URLs. Its content is `- ` and then the Provided Input variable.
2. Add a **URL Encode** action on that text.
3. Put the URL Encode result into the `content=` part of the URL.

The `- ` prefix makes each capture a list item.

## Add it to the home screen

Open the Shortcut's settings and choose Add to Home Screen.

## Sync

Obsidian on the phone syncs only while it is open. After you capture, leave Obsidian in front for a few seconds so the line reaches the Mac.
