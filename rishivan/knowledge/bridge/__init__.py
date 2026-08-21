"""The bridge from the POC ingestion layer into the knowledge pipeline.

The POC already extracted 23 books into `document` / `page` / `source_element`
with high per-element confidence, so there is no OCR work left for BPHS — the
first real stage is reflow. What is missing is shape: the POC emitted six coarse
element types with no verse numbers and no geometry, while `reflow_book()` needs
eleven types plus verse references. Everything that gap requires is derivable
from the text itself, which is why this whole package spends nothing on a model.

One-way and read-only with respect to `document` / `page` / `source_element`:
those tables are the immutable raw layer, and they are the one asset that cannot
be rebuilt. Everything here derives `corpus_page_element` rows from them.
"""
