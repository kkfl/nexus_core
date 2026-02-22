#!/usr/bin/env bash
set -e

# Semantic Version Release Helper

# Ensure we're at repo root
cd "$(dirname "$0")/../../"

if [ ! -f "VERSION" ]; then
  echo "Error: VERSION file not found!"
  exit 1
fi

VERSION=$(cat VERSION | tr -d '[:space:]')
echo "Detected Version: $VERSION"

# Validation
if ! git diff-index --quiet HEAD --; then
  echo "Error: Git working directory is not clean. Commit or stash changes before releasing."
  exit 1
fi

DATE=$(date +%Y-%m-%d)
TAG="v$VERSION"

echo "Applying Release Tag: $TAG ($DATE)"

# 1. Update Changelog Header (if there's an [Unreleased] section)
if grep -q "## \[Unreleased\]" CHANGELOG.md; then
  echo "Promoting [Unreleased] to [$VERSION] - $DATE in CHANGELOG.md..."
  # Use sed to replace the exact Unreleased header with the new Version header
  sed -i.bak "s/## \[Unreleased\]/## \[$VERSION\] - $DATE/" CHANGELOG.md
  rm -f CHANGELOG.md.bak
else
  echo "No [Unreleased] block found in CHANGELOG.md. Assuming already versioned."
fi

# 2. Stage and Commit the release metadata
git add VERSION CHANGELOG.md || true
git commit -m "chore(release): bump to $VERSION" || true

# 3. Create Annotated Tag
git tag -a "$TAG" -m "Release $VERSION" || echo "Tag $TAG might already exist"

echo ""
echo -e "\033[1;32mRelease prepared successfully!\033[0m"
echo -e "Next steps:"
echo "  1. git push origin main"
echo "  2. git push origin $TAG"
