# Distribution And Packaging Plan

Date: 2026-06-30

## A. Staged Distribution Strategy

### Stage 0. Python Local Dev

Current state:

- run with `python run.py companion`
- local SQLite DB
- no installer
- no signing
- no auto-update

Purpose:

- product discovery
- demo
- internal testing

### Stage 1. Internal Alpha Portable

Target:

- portable folder or zip
- README-based execution
- limited invited users
- manual logs

Scope:

- stable local run command
- demo DB kept separate
- no payment

### Stage 2. Windows Portable Zip/Exe

Target:

- downloadable zip/exe
- manual update
- invite-only user tests

Needs:

- app icon
- version info
- data path documentation
- basic error log path
- clear uninstall/delete instructions

### Stage 3. Windows Installer

Target:

- installer
- start menu shortcut
- version management
- basic error logging

Needs:

- installer technology choice
- install path
- data path
- upgrade behavior
- uninstall behavior

### Stage 4. Production Distribution

Target:

- auto-update
- code signing
- crash reporting
- release channel
- macOS feasibility review

Do not start here. Validate demand first.

## B. Download Flow

Landing website should provide:

- download page
- version number
- release notes
- checksum or safety note
- setup guide
- troubleshooting
- support contact

## C. Update Strategy

Initial:

- manual download
- release notes
- visible version number

Later:

- update check
- update notification
- background downloader if justified

Final:

- auto-update
- signed installers
- stable rollback plan

## D. Security And Trust

Required before broad distribution:

- code signing plan
- malware false-positive mitigation
- privacy policy
- local data location documentation
- clear connector permission copy
- support response path

## E. Current Code Preparation

Prepare later:

- app version constant
- release notes document
- logs path
- config path
- data path
- user-visible diagnostics

Do not implement installer or auto-update in the current MVP architecture phase.
