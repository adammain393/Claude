# Mac Setup Summary

## What was set up

### Git
- Git is installed (version 2.50.1)

### GitHub SSH Connection
- SSH key generated at: ~/.ssh/id_ed25519
- Public key added to GitHub account (adammain393)
- Connection verified and working

### Homebrew
- Installed at: /opt/homebrew/bin/brew
- Added to shell profile (~/.zprofile)

### GitHub CLI (gh)
- Installed via Homebrew
- Logged in as: adammain393
- Protocol: SSH

### Cloned Repo
- Repo: git@github.com:adammain393/Claude.git
- Location: ~/Desktop/Claude Code/Claude

## Useful Commands

Clone a repo:
  git clone git@github.com:adammain393/REPO-NAME.git

Check GitHub login:
  gh auth status

Push code to GitHub:
  git add .
  git commit -m "your message"
  git push

## Claude Code in Cursor
- Install extension: search "Claude Code" in Cursor extensions (Cmd+Shift+X)
- Or use this link in your browser: cursor:extension/anthropic.claude-code
- Sign in with your Anthropic account after installing
