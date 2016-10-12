import os
import json

from tinydb import TinyDB, Query, Storage


class FlatDocumentStorage(Storage):
    def __init__(self, path, pkey_field, big_field=None, read_only=False):
        self.path = path
        self.pkey_field = pkey_field
        self.big_field = big_field
        self.read_only = read_only

    def read(self):
        if not os.path.exists(self.path):
            return None

        tables = {}
        for table_name in os.listdir(self.path):
            tbl = {}
            tbl_path = os.path.join(self.path, table_name)
            for doc_name in os.listdir(tbl_path):
                doc_path = os.path.join(tbl_path, doc_name)

                with open(doc_path) as inp:
                    doc, big_field = self.read_doc(inp)

                if big_field is not None:
                    doc[self.big_field] = big_field

                doc[self.pkey_field] = doc_name
                eid = hash(doc[self.pkey_field])

                tbl[eid] = doc
            tables[table_name] = tbl

        return tables

    def read_doc(self, inp):
        buf = inp.read()
        if buf[-1] == '\n':
            buf = buf[:-1]
        parts = buf.split('\n+++\n\n', 1)
        header = json.loads(parts[0])

        big_field = None
        if len(parts) == 2:
            big_field = parts[1] or None

        return header, big_field

    def write(self, data):
        if self.read_only:
            return

        # create database dir
        if not os.path.exists(self.path):
            os.mkdir(self.path)

        # store all tables
        for table_name, table_data in data.items():
            table_path = os.path.join(self.path, table_name)
            if not os.path.exists(table_path):
                os.mkdir(table_path)

            for eid, doc_data in table_data.items():
                key = doc_data.pop(self.pkey_field)

                big_field = None
                if self.big_field is not None:
                    big_field = doc_data.pop(self.big_field, None)

                doc_path = os.path.join(table_path, key)

                with open(doc_path, 'w') as out:
                    self.write_doc(out, big_field, doc_data)

        # FIXME: does not erase tables. too dangerous

    def write_doc(self, out, big_field, data):
        json.dump(data, out)
        out.write('\n+++\n\n')
        if big_field is not None:
            out.write(big_field)
        out.write('\n')


if __name__ == '__main__':
    User = Query()

    db = TinyDB('ffdb', 'name', 'body', storage=FlatDocumentStorage)
    # db.insert({'name': 'John', 'age': 22})

    print(db.search(~(User.name == 'JohnX')))
