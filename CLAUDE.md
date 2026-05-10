# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository

GitHub repo: `git@github.com:adammain393/Claude.git`  
Cloned to: `~/Desktop/Claude Code/Claude`

## Environment

- **Git**: 2.50.1
- **GitHub CLI**: authenticated as `adammain393` via SSH
- **Homebrew**: `/opt/homebrew/bin/brew`
- **Shell**: zsh (`~/.zprofile` holds Homebrew path)

## Git Workflow

```bash
git add <files>
git commit -m "message"
git push
```

Clone other repos from this account:
```bash
git clone git@github.com:adammain393/REPO-NAME.git
```

Check GitHub auth:
```bash
gh auth status
```
