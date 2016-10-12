import os
import json

from tinydb import Storage


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
            for (dir_path, dir_names, fns) in os.walk(tbl_path):
                # determine table-relative path components
                rel_path = os.path.relpath(dir_path, tbl_path)

                components = [] if rel_path == '.' else os.path.split(
                    rel_path)[1:]
                if not fns:
                    continue

                for fn in fns:
                    doc_path = os.path.join(tbl_path, dir_path, fn)
                    doc_name = '/'.join(components + (fn, ))

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
        json_lines = []
        body_lines = []

        # valid states are: pre, json, skip, body
        state = 'pre'

        for line in inp.read().splitlines():
            if state == 'pre':
                if not line:
                    # skip empty lines at the start
                    continue

                if line != '---':
                    raise ValueError('Data file does not start with `---`')

                state = 'json'
                continue

            if state == 'json':
                if line == '---':
                    state = 'skip'
                    continue

                json_lines.append(line)
                continue

            if state == 'skip':
                # skip whitespace after ---

                if not line.strip():
                    continue

                state = 'body'
                # fall through to body:

            if state == 'body':
                body_lines.append(line)
                continue

            raise RuntimeError('unreachable')

        try:
            json_raw = '\n'.join(json_lines)
            header = json.loads(json_raw)
        except ValueError as e:
            raise ValueError(
                'Could not decode JSON {!r}'.format(json_raw)) from e

        big_field = None if not body_lines else '\n'.join(body_lines)

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
