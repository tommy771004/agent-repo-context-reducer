# Graph and index

The native graph represents resolved static imports and reverse dependencies. It is not a runtime call graph. The persistent index stores structural summaries, symbols, entry points, workspaces and ranking inputs. Source parsing can be cached while graph/ranking are rebuilt on sync.
