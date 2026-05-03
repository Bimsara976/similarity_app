// ============================================================
//  mongo-init.js
//  Runs once on first container boot (when the data volume is empty).
//  Creates a dedicated app-level user with readWrite access to
//  the similarity_lk database — separate from the root admin.
// ============================================================

db = db.getSiblingDB('similarity_lk');

db.createUser({
  user: 'similarity_user',
  pwd:  'similarity_pass_2026',     // override via MONGO_APP_PASS in .env
  roles: [
    { role: 'readWrite', db: 'similarity_lk' }
  ]
});

print('MongoDB init: similarity_user created for database similarity_lk');
