# Project history

The project began with Open Library and explored dBooks, LibriVox and Open Textbook Library. Internet Archive was selected because the three independent acquisition methods worked and its Views API supplied engagement labels.

The original Internet Archive pilot used ten items. A 200-item benchmark followed. The first HTML benchmark had parsing defects affecting publication years and timestamp/language formats; those defects were fixed and the same 200 items were collected again.

The original random-fiction training attempt stopped at 400 records. The final training design contains 200 benchmark items plus 600 science fiction, 600 fantasy and 600 mystery/thriller records, collected through the API.

The completed collection and all earlier experiments are preserved in [commit 724af15](https://github.com/Mhmd-Shkeir/Lab-Network-Project/commit/724af154e5e98d8d301622dabfffa01da645a1eb). A verified local backup named `LabNet_before_cleanup_2026-11-20.zip` also preserves the pre-cleanup folder, including ignored historical pages.

The 20 November cleanup removed superseded plans, old-source scripts, validation runs and redundant benchmark CSV copies from the active repository. Final datasets, frozen manifests and the final four collection runs remain. Derived request-time medians were recomputed from unchanged attempt logs, with the prior values recorded in the affected summaries. The code now computes even-sized medians correctly and evaluates a browser retry using the latest attempt's document response.

Collection timings remain distinct from Issa's upcoming network measurements. Cleaning, EDA, ML, networking/security experiments, the report and presentation remain on the project checklist.
