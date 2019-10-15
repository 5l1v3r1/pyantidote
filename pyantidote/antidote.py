#!/usr/bin/env python

import os
import time
import hashlib
import sqlite3
import requests
import threading
from bs4 import BeautifulSoup

from binaryornot.check import is_binary

'''
commentary:
    - `while True: try: v = next(f);; except StopIteration: break` is usually spelled `for v in f:`
    - Your busywaiting loop could use some abstraction. I think modern Pythons even ship a thread pool
    - Your use of FileScanner as a context manager doesn't seem to be doing anything
'''

class DB(object):
    # TODO: Log the URLS it's grabbed hashes from
    # And check the logged urls and skip over logged urls
    # when calling the self.update() function
    def __init__(self, db_fp='data.db'):
        self.db_fp = db_fp
        self.conn = sqlite3.connect(db_fp)
        self.cur = self.conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def __repr__(self):
        return "<SQLite3 Database: {}>".format(self.db_fp)

    def close(self):
        self.conn.commit()
        self.cur.close()
        self.conn.close()

    def create_tables(self):
        self.cur.execute('CREATE TABLE IF NOT EXISTS known_virus_md5_hashes(hash TEXT NOT NULL UNIQUE)')
        self.cur.execute('CREATE TABLE IF NOT EXISTS processed_virusshare_urls(url TEXT NOT NULL UNIQUE)')
        self.conn.commit()

    def drop_tables(self):
        self.cur.execute('DROP TABLE IF EXISTS known_virus_md5_hashes')
        self.cur.execute('DROP TABLE IF EXISTS processed_virusshare_urls')
        self.conn.commit()

    def add_hash(self, md5_hash):
        '''
        adds md5 hash to the database of known virus hashes
        '''
        try:
            self.cur.execute('INSERT INTO known_virus_md5_hashes VALUES (?)', (md5_hash,))
        except sqlite3.IntegrityError as e:
            if 'UNIQUE' in str(e):
                pass # Do nothing if trying to add a hash that already exists in the db
            else:
                print(e)
                raise sqlite3.IntegrityError

    def add_processed_url(self, url):
        '''
        adds a url to the database of processed urls (url containing a list of known virus hashes)
        '''
        self.cur.execute('INSERT INTO processed_virusshare_urls VALUES (?)', (url,))

    def is_known_hash(self, md5_hash) -> bool:
        '''
        checks hash against the db to determine if the hash is a known virus hash
        '''
        self.cur.execute('SELECT hash FROM known_virus_md5_hashes WHERE hash = (?)', (md5_hash,))
        return self.cur.fetchone() is not None

    def is_processed_url(self, url) -> bool:
        self.cur.execute('SELECT url FROM processed_virusshare_urls WHERE url = (?)', (url,))
        return self.cur.fetchone() is not None

    def reset(self, output=False):
        '''
        reformats the database, think of it as a fresh-install
        '''
        self.drop_tables()
        self.create_tables()
        self.update(output)

    def update(self, output=False):
        '''
        updates the sqlite database of known virus md5 hashes
        '''
        urls = self.get_virusshare_urls()
        for n, url in enumerate(urls):
            if output:
                reprint(f"Downloading known virus hashes {n}/{len(urls)}")
            if not self.is_processed_url(url):
                hash_gen = self.get_virusshare_hashes(url)
                for md5_hash in hash_gen:
                    self.add_hash(md5_hash)
                self.add_processed_url(url)
            self.conn.commit()

    def get_virusshare_urls(self) -> list:
        '''
        returns a list of virusshare.com urls containing md5 hashes
        '''
        r = requests.get('https://virusshare.com/hashes.4n6')
        soup = BeautifulSoup(r.content, 'html.parser')
        return ["https://virusshare.com/{}".format(a['href']) for a in soup.find_all('a')][6:-2]

    def get_virusshare_hashes(self, url) -> str:
        '''
        parses all the md5 hashes from a valid virusshare.com url
        '''
        r = requests.get(url)
        for md5_hash in r.text.splitlines()[6:]:
            yield md5_hash


class FileScanner(object):
    def __init__(self, max_threads=10):
        self.max_threads = max_threads
        self.bad_files = []

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        pass
        # self.stop()

    def get_binary_files_generator(self, folder) -> str:
        '''
        :param folder: directory to resursively check for binary files
        :return: generator of all binary files (str == full path)
        '''
        for folder_name, sub_folder, filenames in os.walk(folder):
            for f in filenames:
                f = f"{folder_name}/{f}"
                if is_binary(f):
                    yield os.path.abspath(f)

    def get_md5(self, fp) -> str:
        '''
        :param fp: full path to a file
        :return: the md5 hash of a file
        '''
        md5_hash = hashlib.md5()
        with open(fp, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def compare_against_database(self, fp):
        with DB() as db:
            md5_hash = self.get_md5(fp)
            if db.is_known_hash(md5_hash):
                self.bad_files.append(os.path.abspath(fp))

    def get_root_directory(self):
        '''
        returns the root directory where this script resides
        IE:
        C:\\Users\Admin\Desktop\code\pyantidote\pyantidote\antidote.py -> C:\\
        /mnt/c/Users/Admin/Desktop/code/pyantidote/pyantidote/antidote.py -> /
        '''
        pass

    def scan(self, folder):
        start_time = time.time()
        fp_gen = self.get_binary_files_generator(folder)
        count = 0
        try:
            while True:
                if threading.active_count() < self.max_threads:
                    t = threading.Thread(target=self.compare_against_database, args=(next(fp_gen), ))
                    t.start()
                    count += 1
                    reprint(f'Scanning Files - Threads: {threading.active_count()}    Files Scanned: {count}     ')
                else:
                    time.sleep(0.01)
        except StopIteration:
            end_time = time.time()
            print(f"scanned {count} files in {end_time - start_time} seconds")
            for f in self.bad_files:
                print(f"INFECTED - {f}")


def reprint(s):
    print(s, end='')
    print('\r' * len(s), end='')


def Main():
    # Testing for now
    # with DB() as db:
    #     db.update(True)
    with FileScanner(20) as fsc:
        fsc.scan('/mnt/c/PHANTASYSTARONLINE2')


if __name__ == '__main__':
    Main()
