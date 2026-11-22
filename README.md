# spacebourne-2-save-editor
UNOFFICIAL save editor for SpaceBourne 2

A lightweight save editor for [SpaceBourne 2](https://store.steampowered.com/app/1646850/SpaceBourne_2/), built with Python and Tkinter and distributed as a standalone Windows executable.

The tool lets you modify selected character progression values and add ships to your save. It is designed to provide a straightforward graphical interface while keeping a backup of the original save before changes are written.

> [!WARNING]
> Editing save files always carries a risk of data loss or corruption. **Close SpaceBourne 2 before using the editor**, and keep independent backups of saves you care about.

## Features

### Character

- **Credits:** Add either 500,000 or 3,000,000 TY.
- **Experience:** Add 100,000 or 1,000,000 XP to the Pilot, Soldier, or Explorer progression.
- **Levels:** Adjust the level of each progression area.
- **Attribute points:** Level increases grant 3 attribute points per level. Lowering a level does not remove previously accumulated attribute points.

### Ships

- Add ships using templates provided by `sb2_ships_catalog.json`.
- Select a ship class from the available catalog.
- The editor can create a missing ship class entry when needed.
- Added ships are assigned to the player's ownership and placed in the Freelancers Guild, in the N25 system (Oblivrax).
- Ship templates are added with a tier from 1 to 4 and a level no higher than the current Pilot level.

### Save protection

- Creates a backup of the selected save before writing changes.
- Compresses the modified save and verifies the result before replacing the original file.

## Getting Started

### Requirements

- Windows

The program is distributed as a standalone `.exe`. **You do not need to install Python, Tkinter, or any additional dependencies** to run it.

### Installation

1. Download the latest `.exe` from the repository's **Releases** page.
2. Double-click the `.exe` to launch the editor.

No installer or additional setup is required.

If the catalog file is unavailable, character editing can still be used, but the ship catalog and ship-adding features will not be available.

## Usage

1. Close **SpaceBourne 2** if it is running.
2. Launch the editor by double-clicking its `.exe` file.
3. Select the save you want to edit from the detected save files.
4. Choose the character values or ship-related changes you want to apply.
5. Review your changes before saving.
6. Save the modified file. The editor creates a backup before replacing the original save.

### Save locations

The editor looks for save files in the game's default Windows save directory:

```text
%LOCALAPPDATA%\SB2\Saved\SaveGames
```

Backups are stored separately:

```text
%LOCALAPPDATA%\SB2\SaveEditor_Backups
```

## Compatibility

The editor relies on the save-file structure used by the current version of SpaceBourne 2. A game update that changes this structure may affect compatibility or cause some editing features to stop working.

The level editor is limited to values up to **99**. This is an editor-side limit; the game's actual maximum level has not been established. Numeric values are also constrained by the signed 32-bit integer range.

## Project Files

| File | Description |
|---|---|
| `.exe` file | Standalone application used to launch the editor on Windows. |
| `sb2_save_editor.py` | Python source code for the application. |
| `sb2_ships_catalog.json` | Ship-template catalog used by the ship-adding feature. |

## Disclaimer

This project is an unofficial, community-made utility and is not affiliated with, endorsed by, or supported by the developers or publishers of SpaceBourne 2.

Use it at your own risk. Always keep backups of your save files. The author is not responsible for lost, corrupted, or otherwise damaged saves resulting from the use of this tool.

## License

This project is licensed under the MIT License. You are free to use, modify, and distribute this software, provided that the original copyright notice and license are included.

See **[LICENSE](LICENSE)** for the full license text.
