# FreeCAD GUI history branch patch review

Review date: 2026-10-23 UTC. Target: FreeCAD commit `4fd3bf320d9566a27e60069fc8387448aaa3a094` (the 1.1.4 host used for the preserved failure).

## Recommendation

Proceed with an isolated source build of the existing three-line candidate in `Gui::Document::slotTransactionRemove`. The insertion removes every pending reference to a provider before removal transfers it to a transaction or deletes it. It changes neither application transaction ownership nor Undo/Redo history. The existing expression `d->_redoViewProviders.remove(it->second)` has the correct type; the local variable named `viewProvider` has the base type `ViewProvider*`, while the queue and map value use `ViewProviderDocumentObject*`.

This is approval of the narrow source change for compilation and regression testing. It is not a runtime fix claim, sanitizer result, Windows acceptance result, or upstream approval. The original failing sequence must still be rerun against the resulting host binary.

## Ownership and removal paths

The private queue contains raw `ViewProviderDocumentObject*` values. `slotNewObject` queues a provider when the GUI document is transacting; both GUI Undo and GUI Redo enable that flag. Only GUI Redo subsequently traverses and clears the queue. Several consecutive Undo operations can therefore retain references, including duplicate references, until a later Redo.

`App::Document::_removeObject` emits `signalTransactionRemove` for the removed object. It passes the active transaction ordinarily and a null transaction during rollback. The GUI slot removes the provider from the live object and Coin maps, then either calls `transaction->addObjectNew(viewProvider)` or directly deletes the provider. The candidate insertion precedes both operations and all map erasure.

The location matters for two separate lifetime endings:

1. `Transaction::addObjectNew` can detach the provider and make the transaction its owner. A later branch discard deletes detached objects owned by the discarded transaction.
2. `Transaction::addObjectNew` can immediately delete a provider that already has the matching `Del` entry; a null transaction also directly deletes it.

Removing the queue entry before ownership transfer covers both. `std::list::remove` removes all references equal to the pointer, rather than just the first reference.

The provider's `detachFromDocument` sets its `Detach` status, and `isAttachedToDocument` returns the inverse of that status. This is the predicate the transaction destructor uses before freeing a detached owned object. The subsequent source-supported causal path is therefore consistent with the preserved crash in `Gui::Document::handleChildren3D`.

Normal restoration remains unchanged: the application reattaches the transaction-owned provider and emits the new-object signal; GUI `slotNewObject` restores its representation, calls `handleChildren3D`, and queues it again when a GUI history operation is active. A removed provider no longer needs pending 3D updates while it is absent from the live document.

## Other deletion paths inspected

Within the pinned `Gui/Document.cpp`, the live provider map is erased by the transaction removal slot. Other direct deletion sites have a different lifetime:

| Path | Effect on this queue |
| --- | --- |
| Invalid provider override during new-provider construction | Provider has not yet been inserted into the live maps or queued. |
| GUI document destruction | The entire document implementation, including the queue, is destroyed. No subsequent queue drain exists for that document. |
| Annotation provider removal | Annotations use a separate map and are not added by `slotNewObject` to this queue. |
| Object moved between documents | Native object removal invokes `_removeObject`; the removal slot is reached for the source document. |
| Transaction abort | Removal during rollback emits the slot with a null transaction. |

No additional production change is required by the specific ownership defect reviewed here. This conclusion does not claim that arbitrary reentrant custom `claimChildren3D` callbacks are safe. It also does not refactor the broader design in which Undo leaves pending 3D work for a later Redo. Those are separate concerns and should not be silently mixed into a narrow fix.

## Regression requirements

The following behaviors should be checked on the compiled host. Process survival alone is insufficient: record actual document content, Undo/Redo availability, and successful close or save/reopen where applicable.

| Case | Required evidence |
| --- | --- |
| Original no-addon reproduction | Create, delete, GUI Undo twice, new Label edit, GUI Undo, GUI Redo in the original order; final label correct. |
| Original 3117 workflow | Unmodified archived catalogue material lifecycle followed by the shared type edit and GUI Undo/Redo. |
| Native object varieties | App::FeaturePython with no custom proxy and ordinary Part::Feature. |
| Unbranched history | Create/delete, GUI Undo twice, GUI Redo twice; object and history state match each operation. |
| Retained older edit | An earlier unrelated edit remains in the Undo stack and can still be undone/redone after the new branch. |
| Repeated cycles | Several independent create/delete/branch cycles without clearing history. |
| Aborted deletion | Restore the deleted provider through GUI Undo, remove it in a new transaction, abort that transaction, and continue normal GUI history. |
| Aborted creation | Create a temporary object in a transaction and abort; no temporary object or extra committed entry remains. |
| Native 3D children | Use native App::Part with native Part::Feature children, optionally nested App::Part; verify child membership and display after restoration. |
| Close with pending work | Restore a provider through GUI Undo and close the disposable document before any Redo; another document remains usable. |

`App::Part` is the appropriate native 3D grouping case. The pinned `ViewProviderGeoFeatureGroupExtension::extensionClaimChildren3D` explicitly claims the group's members in 3D. A plain `App::DocumentObjectGroup` alone does not establish equivalent 3D child-root coverage.

## Patch application and provenance

The exact downloaded host `src/Gui/Document.cpp` has 3,186 CRLF line endings and SHA-256 `8c2efdcd569b4c1a4fe378bb756a6d8b9bc4b0faf0a764e2efff0933350a47b6`. The old illustrative patch uses LF. A git checkout may normalize the source; verify actual patch application and final diff instead of assuming line-ending compatibility. Preserve source bytes other than the intended insertion.

`apply-reviewed-patch.py` is a strict optional helper: it accepts only the exact pinned source or its LF-normalized equivalent, inserts the same candidate once, preserves the source's existing newline style, and prints before/after hashes. It does not act on any source file unless explicitly passed its path. It is not a binary patch and performs no history operation.

Primary source references:

- [Gui/Document.cpp](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/Document.cpp), queue at line 119, append at 1048–1052, removal at 1176–1198, history at 2955–2987.
- [App/Document.cpp](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/App/Document.cpp), transaction abort at 525–546, native removal at 3267–3369.
- [App/Transactions.cpp](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/App/Transactions.cpp), destructor at 55–89 and ownership transfer at 207–232.
- [Gui/ViewProviderDocumentObject.cpp](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/ViewProviderDocumentObject.cpp), attachment status at 115–126.
- [Gui/ViewProviderGeoFeatureGroupExtension.cpp](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Gui/ViewProviderGeoFeatureGroupExtension.cpp), native 3D group claim at 65 onward.

Additional source files downloaded for this review are recorded with immutable URLs and SHA-256 in `additional-source-manifest.json`. Original host sources and prior failure evidence remain unchanged.
