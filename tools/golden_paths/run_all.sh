#!/usr/bin/env bash

set -e

echo "============================================="
echo "   NEXUS CORE V1 : GOLDEN PATHS AUTOMATION   "
echo "============================================="

if [ ! -f .env ]; then
  if [ -f env.example ]; then
    cp env.example .env
    echo "Created .env from env.example. Please review settings."
  else
    echo "Error: Need a .env file to run endpoints."
    exit 1
  fi
fi

source .env

for path_script in paths/*.sh; do
  echo ""
  echo "---------------------------------------------"
  bash "$path_script"
  echo "---------------------------------------------"
done

echo ""
echo -e "\033[1;32mALL GOLDEN PATHS EXECUTED SUCCESSFULLY!\033[0m"
echo "Verify the outcomes by navigating to the Nexus Portal at http://localhost:3000"
