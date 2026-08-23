# Publishing to New Package Managers

This document outlines the process for publishing Bruno to new package managers.

## Requirements

- Access to the package manager's publishing infrastructure
- Proper signing keys and credentials
- Updated package metadata

## Process

### 1. Update Package Metadata

Update the `package.json` file with the correct version and metadata:

```json
{
  "name": "bruno",
  "version": "1.0.0",
  "description": "A lightweight, open-source API client built for developers.",
  "keywords": ["api", "client", "postman", "rest", "http"]
}
```

### 2. Build Distribution Packages

```bash
# Build for different platforms
npm run build

# Generate installers for desktop platforms
npm run tauri build
```

### 3. Publish to Package Managers

#### npm

```bash
npm publish
```

#### Homebrew (macOS)

Create a formula and submit a pull request to homebrew-core.

#### AUR (Arch Linux)

Create a PKGBUILD and submit to the AUR.

#### Chocolatey (Windows)

Submit package to Chocolatey community repository.

## Verification

After publishing, verify that:

- The package is available on the package manager's website
- Installation works correctly
- Version numbers match across all platforms
- Documentation links are working

## Support

For questions about publishing, contact the Bruno maintainers at maintainers@usebruno.com.