# FreeCAD GUI history branch: source review

Review date: 2026-10-23 UTC. This is a read-only source diagnosis, not a tested FreeCAD patch. No application or repository production code was changed, and no upstream issue or other external message was sent.

## Finding

The exact host source contains a raw view-provider pointer queue whose lifetime can outlast the transaction that owns a queued provider. GUI Undo can append to this queue, while only GUI Redo drains it. A new transaction discards the redo branch and can destroy a queued provider; the later GUI Redo dereferences the queued pointer. This is a source-supported explanation for the independently reproduced crash in `Gui::Document::handleChildren3D+0x3a`.

The relevant queue lifecycle remains unchanged in the pinned upstream main commit reviewed below. No public Python GUI API was found that safely clears this queue while preserving the complete existing Undo history. The current host therefore remains blocked for this history-branch workflow. This review does not establish that a weekly build, another operating system, or another FreeCAD version is safe.

## Revisions and primary sources

The host source is commit [`4fd3bf320d9566a27e60069fc8387448aaa3a094`](https://github.com/FreeCAD/FreeCAD/commit/4fd3bf320d9566a27e60069fc8387448aaa3a094). Upstream main resolved to [`dc1ab881ca0bbea9735e92938a660acee339679e`](https://github.com/FreeCAD/FreeCAD/commit/dc1ab881ca0bbea9735e92938a660acee339679e), committed at 2026-10-23T04:26:36Z. Downloading `Document.cpp` at that immutable SHA produced the same bytes as both the fetched `main` and `master` URLs.

| Source | Relevant host lines | Source observation |
| --- | ---: | --- |
| [Gui/Document.cpp: queue](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/Document.cpp#L119) | 119 | Private implementation stores a list of raw `ViewProviderDocumentObject*`. |
| [Gui/Document.cpp: restoration](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/Document.cpp#L1048-L1052) | 1048–1052 | `slotNewObject` appends the provider when the GUI document's transaction flag is set. |
| [Gui/Document.cpp: removal](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/Document.cpp#L1176-L1198) | 1176–1198 | `slotTransactionRemove` removes map entries and transfers/deletes the provider without removing it from the queue. |
| [Gui/Document.cpp: history](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/Document.cpp#L2955-L2987) | 2955–2987 | Both Undo and Redo set the GUI transaction flag. Only Redo processes and clears the queue. |
| [Gui/Document.cpp: dereference](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/Document.cpp#L2995-L3002) | 2995–3002 | `handleChildren3D` calls through the pointer after a null check; a dangling pointer can still be non-null. |
| [App/Document.cpp: branch discard](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/App/Document.cpp#L367) | 367; 450–462 | Opening a transaction clears redo transactions; the clearing loop deletes them. |
| [App/Transactions.cpp: ownership](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/App/Transactions.cpp#L55-L89) | 55–89; 207–232 | A transaction deletes detached objects it owns with `New` status; adding a new transaction entry detaches its object. |

Two short source excerpts identify the queue operation and its only drain:

```cpp
d->_redoViewProviders.push_back(pcProvider);

for (auto it : d->_redoViewProviders) {
    handleChildren3D(it);
}
d->_redoViewProviders.clear();
```

The complete source files remain in the read-only review cache at `/tmp/bim3117-v050-exchange/freecad-lifecycle-source`. `source-manifest.json` records their official URLs, immutable commits, exact sizes, and SHA-256 hashes. The host `Gui/Document.cpp` hash is `8c2efdcd569b4c1a4fe378bb756a6d8b9bc4b0faf0a764e2efff0933350a47b6`; pinned main is `f7474963f2ca4d27653c6fe387ccdb49e8727f15bfd1f33581a93dd39563051b`.

## Failure sequence explained by the source

1. Create a disposable object in one transaction and delete it in a second transaction.
2. GUI Undo restores the deletion. The restored provider is appended because the GUI transaction flag covers Undo as well as Redo.
3. A second GUI Undo removes the originally created object. Transaction removal detaches the provider, but its queued pointer remains.
4. Open a new Label-edit transaction on a surviving object. Discarding the redo branch destroys the detached disposable object and its transaction-owned provider.
5. Undo and then Redo the Label edit. GUI Redo drains the earlier queue and reaches a freed provider.

Steps 1–5 are an inference connecting the exact source paths to the independent native reproducer. This review did not run a memory sanitizer or prove a particular heap address. The independent native probes, logs, and no-addon reproducer are packaged separately in the parent `host-history-branch` directory. They establish the runtime failure; the source explains a compatible ownership defect. The queue mechanism is not an event-loop timer or Qt DeferredDelete list.

## Public lifecycle APIs examined

| API or proposed approach | Evidence and limit |
| --- | --- |
| `Gui.updateGui()` | [ApplicationPy.cpp, 984–992](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/ApplicationPy.cpp#L984-L992) only processes Qt events. It does not access the queue. |
| `Gui.activeDocument().update()` | [DocumentPyImp.cpp, 215–229](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/DocumentPyImp.cpp#L215-L229) invokes `onUpdate`; [Document.cpp, 2451–2466](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/Document.cpp#L2451-L2466) updates views without clearing this queue. |
| Standard Undo/Redo commands or view messages | [CommandDoc.cpp, 1096–1101 and 1141–1146](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/CommandDoc.cpp#L1096-L1146) route to the view; [View3DInventor.cpp, 446–452](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/View3DInventor.cpp#L446-L452) calls GUI Undo/Redo with exactly one step. It offers no queue-only operation. |
| Hypothetical zero-step GUI Redo | [Document.cpp, 2866–2870](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/Document.cpp#L2866-L2870) rejects zero steps before reaching the drain, even in C++. The GUI Python wrapper inspected has no Undo/Redo method; the native probe independently confirmed this. |
| Application document `undo()`/`redo()` | [App/DocumentPyImp.cpp, 601–620](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/App/DocumentPyImp.cpp#L601-L620) calls the application document directly. That does not clear an already queued GUI pointer and does not replace every normal GUI history entry point. It is not an established compatibility fix. |
| Clearing history or disabling Undo | This removes the history required by the product. [App/Document.cpp, 613–641 and 688–695](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/App/Document.cpp#L613-L695) confirms the destructive history operation. It is not a solution to the requested workflow. |

The queue and its handler are implementation details, not an exposed Python lifecycle contract. `handleChildren3D` and the implementation pointer are private in [Gui/Document.h, 346–359](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/Document.h#L346-L359).

## Upstream main comparison

At the pinned main SHA, `undo`, `redo`, `slotTransactionRemove`, `slotUndoDocument`, and `slotRedoDocument` are text-identical to the host implementations. The queue declaration and append condition remain the same. The changes to `onUpdate` are iteration syntax; changes to `handleChildren3D` are warning-format syntax. Neither changes the ownership path above. See [pinned main history implementation](https://github.com/FreeCAD/FreeCAD/blob/dc1ab881ca0bbea9735e92938a660acee339679e/src/Gui/Document.cpp#L3015-L3062) and the machine-readable method comparison in the manifest.

This is a source comparison, not a test of a current upstream binary. It provides no reason to recommend a weekly build merely because it is newer.

## Optional upstream patch direction — untested

A narrowly scoped candidate is to remove a provider from the pending list in `slotTransactionRemove`, before it is detached or handed to a transaction. The intended invariant is that a provider removed from the live document cannot remain in a queue later traversed as live pointers. Such a change would leave the transaction history itself intact.

`untested-provider-removal.patch` illustrates that single insertion against the exact host source. It has not been applied, compiled, or run, and is not included in BIM3117 production code. It requires core review and regression tests for restored/deleted objects, grouped history, nested child providers, aborts, and deletion during repeated Undo/Redo before it can be treated as a fix. A more complete upstream design may use live-object identities or drain pending provider work consistently after both directions; that design was not evaluated here.

Until a corrected host is actually validated with the native reproducer and full GUI workflow, retain the compatibility blocker and preserve the user's Undo history.
