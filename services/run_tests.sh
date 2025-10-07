#!/bin/bash

# Run test suite

echo "=========================================="
echo "Running Test Suite"
echo "=========================================="
echo ""

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "❌ Virtual environment not found"
    exit 1
fi

# Install test dependencies
pip install pytest pytest-asyncio pytest-cov pytest-mock

# Run tests with coverage
echo "Running tests with coverage..."
echo ""

pytest tests/ \
    -v \
    --cov=. \
    --cov-report=html \
    --cov-report=term \
    --cov-config=.coveragerc

TEST_EXIT_CODE=$?

echo ""
echo "=========================================="

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ All tests passed!"
    echo "Coverage report: htmlcov/index.html"
else
    echo "❌ Some tests failed"
fi

echo "=========================================="
echo ""

exit $TEST_EXIT_CODE