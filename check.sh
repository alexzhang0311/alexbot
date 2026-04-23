#!/bin/bash
set -e
echo "🔍 Running pre-deploy checks..."

echo "  [1/3] Python syntax check..."
find backend/app -name "*.py" | xargs python3 -m py_compile
echo "  ✅ Python syntax OK"

echo "  [2/3] Docker Compose validation..."
docker-compose config --quiet
echo "  ✅ docker-compose.yml OK"

echo "  [3/3] Running unit tests..."
cd backend
pip install -q -r requirements.txt -r tests/requirements.txt 2>/dev/null
python3 -m pytest tests/ -q --tb=no
cd ..
echo "  ✅ All tests passed"

echo ""
echo "✅ All checks passed! Ready to deploy."
