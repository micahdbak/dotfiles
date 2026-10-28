# dotfiles

My personal collection of configuration files for Linux and macOS, plus
resources for AI agents (skills, conventions).

## Config

Machine configuration files, mirroring where they live on a system.

- `config/nvim/` - Neovim config (goes to `~/.config/nvim/`). Uses
  lazy.nvim as the plugin manager; current plugins are treesitter and
  the vague colorscheme. Base options live in `init.lua`.
- `config/dwl/` - startup scripts for the dwl Wayland compositor (goes
  to `~/.config/dwl/`). `run.sh` starts dwl piped through slstatus;
  `autostart.sh` finalizes the uwsm session and sets the wallpaper
  with swaybg.
- `.zprofile` - zsh login profile. Runs fastfetch, aliases `vim` to
  `nvim`, and aliases `dwl` to launch the compositor through uwsm.

## Agents

Resources for AI agents, under `agents/`.

- `agents/skills/` - Agent Skills in the portable form (one directory
  per skill, each with a `SKILL.md`). Current skills:
  - `tmux-interactive-sessions` - driving persistent interactive
    terminals (SSH chains, REPLs, TUIs, long-running commands) from a
    non-interactive shell using tmux.
  - `tscon-know-how` - building, debugging, and explaining apps with
    the `@micahdb/tscon` WebGL2 text-mode graphics library.
- `agents/install.sh` - copies everything under `agents/skills/` into
  `~/.agents/skills/`. Run after adding or editing a skill.
- `agents/SKILLS.md` - conventions all skills in this repo must follow.
