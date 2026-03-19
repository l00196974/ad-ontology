#!/bin/bash
# Fix TypeScript type errors for req.params

sed -i 's/const { sessionId } = req.params;/const sessionId = req.params.sessionId as string;/g' src/server.ts
sed -i 's/const { id } = req.params;/const id = req.params.id as string;/g' src/server.ts

echo "Type fixes applied"
