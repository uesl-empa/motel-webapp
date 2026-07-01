#!/bin/bash

GRAPHDB_HOST=${GRAPHDB_HOST:-graphdb}
GRAPHDB_PORT=${GRAPHDB_PORT:-7200}
GRAPHDB_REPO_NAME=${GRAPHDB_REPO_NAME}

REPO_HTTP_STATUS=$(curl -o /dev/null -s -w "%{http_code}" -i "${GRAPHDB_HOST}:${GRAPHDB_PORT}/rest/repositories/${GRAPHDB_REPO_NAME}")

if [ "${REPO_HTTP_STATUS}" -eq "404" ]; then

    # Create repository definition file
    sed "s/__GRAPHDB_REPO_NAME__/${GRAPHDB_REPO_NAME}/g" /api/repo-config.ttl.template > /tmp/repo-config.ttl

    echo ">>> Create new repository"
    curl -s -X POST "${GRAPHDB_HOST}:${GRAPHDB_PORT}/rest/repositories" -H "Content-Type: multipart/form-data" -F "config=@/tmp/repo-config.ttl"

    echo ">>> Empty repository created successfully"

elif [ "${REPO_HTTP_STATUS}" -eq "200" ]; then

  echo ">>> Repository already exixts"

else

  echo ">>> Error creating repository - Server returned ${REPO_HTTP_STATUS}"
  exit 1

fi
