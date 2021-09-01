#!/usr/bin/env python


import os
import re
import shutil
import sqlite3
from collections import defaultdict

import numpy as np
import pandas as pd
from Bio import Phylo, SeqIO, AlignIO
from Bio.Align import MultipleSeqAlignment
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

META_FILE = "/Data4/Trimed_seq/metadata-5.tsv"
MSA_FILE = "/Data4/Trimed_seq/cleaned.fasta"
MSA_FILE2 = "/Data4/Trimed_seq/combined.fasta"
SQLITE_FILE = "/Data4/Trimed_seq/sars2.db"

TREES_DIR = "trees"
OUT_DIR = "renamed_trees"

if os.path.exists(OUT_DIR):
    shutil.rmtree(OUT_DIR)
os.mkdir(OUT_DIR)


if os.path.exists(SQLITE_FILE):
    os.remove(SQLITE_FILE)

conn = sqlite3.connect(SQLITE_FILE)
cur = conn.cursor()

with conn:
    cur.execute('''
        CREATE TABLE records (
            accession TEXT PRIMARY KEY,
            sequence TEXT NOT NULL
        )
    ''')

with conn:
    for fn in (MSA_FILE, MSA_FILE2):
        for record in SeqIO.parse(fn, "fasta"):
            (accession, ) = re.findall(r"EPI_ISL_[0-9]+", record.description)
            try:
                cur.execute(
                    "INSERT INTO records VALUES (:accession, :sequence)",
                    { "accession": accession, "sequence":  str(record.seq) }
                )
            except sqlite3.IntegrityError:
                print(accession)


matched_files = defaultdict(list)
for fn in os.listdir(TREES_DIR):
    m = re.findall(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", fn)
    if m:
        (date_time, ) = m
        matched_files[date_time].append(fn)


missed = set()

for date_time, (fn, fn2) in matched_files.items():
    if fn.endswith("nwk"):
        tree_fn = os.path.join(TREES_DIR, fn)
        meta_fn = os.path.join(TREES_DIR, fn2)
    else:
        tree_fn = os.path.join(TREES_DIR, fn2)
        meta_fn = os.path.join(TREES_DIR, fn)
    tree = Phylo.read(tree_fn, "newick")
    metadata = pd.read_csv(meta_fn, sep="\t", index_col=0, quoting=3)
    n_drop = 0
    out_seqs = []
    n_tips = len(tree.get_terminals())
    for tip in tree.get_terminals():
        seqname = tip.name
        tip.name = metadata.loc[tip.name, "gisaid_epi_isl"]
        if tip.name is None:
            print(seqname)
        cur.execute("SELECT sequence FROM records WHERE accession=?", (tip.name, ))
        res = cur.fetchone()
#         print(tip.name, res)
        if res is None:
            tree.prune(tip)
            missed.add(tip.name)
            n_drop += 1
        else:
            (sequence, ) = res
            out_seqs.append(SeqRecord(
                Seq(sequence),
                id=tip.name,
                description=""
            ))
#         break
    print(date_time, n_tips, n_drop)
    out_dir = os.path.join(OUT_DIR, date_time)
    if not os.path.exists(out_dir):
        os.mkdir(out_dir)
    for tip in tree.get_terminals():
        if tip.name is None:
            tree.prune(tip)
    out_seqs = MultipleSeqAlignment(out_seqs)
    AlignIO.write(out_seqs, os.path.join(out_dir, date_time + ".fasta"), "fasta")
    Phylo.write(tree, os.path.join(out_dir, date_time + ".nwk"), "newick")


missed.discard(np.nan)

with open("missed.csv", "w") as f:
    f.write("\n".join(missed))
    f.write("\n")

len(missed)

