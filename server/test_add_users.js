#!/usr/bin/env node
import { initDb, addUser, getUserByUsername, listUsers, updateUser, removeUser } from './src/db.js';

async function run() {
  try {
    console.log('TEST: initDb');
    await initDb();
    console.log('TEST: initDb done');

    console.log('TEST: addUser testuser');
    const addRes = addUser({ username: 'testuser', password: 'plain123', displayName: 'Test User' });
    console.log('addUser result:', JSON.stringify(addRes));

    console.log('TEST: getUserByUsername testuser');
    const user = getUserByUsername('testuser');
    console.log('getUserByUsername:', JSON.stringify(user));

    console.log('TEST: addUser duplicate');
    const addRes2 = addUser({ username: 'testuser', password: 'plain123', displayName: 'Test User' });
    console.log('addUser duplicate result:', JSON.stringify(addRes2));

    console.log('TEST: listUsers');
    const users = listUsers({ limit: 10, offset: 0 });
    console.log('listUsers:', JSON.stringify(users));

    console.log('TEST: login check');
    if (!user) {
      console.log('login: user not found');
    } else if (user.password_hash === 'plain123') {
      console.log('login: success');
    } else {
      console.log('login: failed');
    }

    console.log('TEST: updateUser displayName');
    const upd = updateUser('testuser', { displayName: 'Updated Name' });
    console.log('updateUser result:', JSON.stringify(upd));
    console.log('after update:', JSON.stringify(getUserByUsername('testuser')));

    console.log('TEST: removeUser');
    const rem = removeUser('testuser');
    console.log('removeUser result:', JSON.stringify(rem));
    console.log('after remove:', JSON.stringify(getUserByUsername('testuser')));

    console.log('TEST: done');
  } catch (err) {
    console.error('TEST ERROR', err);
    process.exit(1);
  }
}

run();
