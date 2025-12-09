#!/bin/bash
# Deployment script for v0.4.0
# Run this script to deploy the package

set -e  # Exit on error

echo "🚀 SQLMesh DAG Generator - Deployment Script v0.4.0"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Clean
echo -e "${YELLOW}Step 1: Cleaning old builds...${NC}"
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
rm -rf build/ dist/ *.egg-info/
echo -e "${GREEN}✓ Clean complete${NC}"
echo ""

# Step 2: Run tests
echo -e "${YELLOW}Step 2: Running tests...${NC}"
python -m pytest tests/ -q
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed${NC}"
else
    echo -e "${RED}✗ Tests failed! Aborting deployment.${NC}"
    exit 1
fi
echo ""

# Step 3: Build
echo -e "${YELLOW}Step 3: Building package...${NC}"
python -m build
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Build complete${NC}"
    echo "Built packages:"
    ls -lh dist/
else
    echo -e "${RED}✗ Build failed!${NC}"
    exit 1
fi
echo ""

# Step 4: Check package
echo -e "${YELLOW}Step 4: Checking package validity...${NC}"
python -m twine check dist/*
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Package is valid${NC}"
else
    echo -e "${RED}✗ Package validation failed!${NC}"
    exit 1
fi
echo ""

# Step 5: Upload (ask for confirmation)
echo -e "${YELLOW}Step 5: Ready to upload to PyPI${NC}"
echo ""
echo "You have two options:"
echo "  1. Upload to TestPyPI (recommended first)"
echo "  2. Upload to production PyPI"
echo "  3. Skip upload (just build)"
echo ""
read -p "Enter choice (1/2/3): " choice

case $choice in
    1)
        echo -e "${YELLOW}Uploading to TestPyPI...${NC}"
        python -m twine upload --repository testpypi dist/*
        echo -e "${GREEN}✓ Uploaded to TestPyPI${NC}"
        echo ""
        echo "Test installation:"
        echo "  pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple sqlmesh-dag-generator==0.2.1"
        ;;
    2)
        echo -e "${YELLOW}Uploading to production PyPI...${NC}"
        python -m twine upload dist/*
        echo -e "${GREEN}✓ Uploaded to PyPI${NC}"
        echo ""
        echo "Install with:"
        echo "  pip install sqlmesh-dag-generator==0.2.1"
        ;;
    3)
        echo -e "${YELLOW}Skipping upload${NC}"
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}=================================================="
echo "🎉 Deployment script complete!"
echo "==================================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Git commit and tag: git tag -a v0.4.0 -m 'Release v0.4.0'"
echo "  2. Push to GitHub: git push origin main && git push origin v0.4.0"
echo "  3. Create GitHub release"
echo "  4. Announce on social media"
echo ""
echo "See DEPLOYMENT_GUIDE_V0.2.0.md for detailed instructions."

