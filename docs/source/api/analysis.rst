analysis — SCM analytics (v0.5)
================================

pandas-native analytics layer. All analyzers take the DataFrames emitted by
:func:`anno_save_analyzer.analysis.to_frames` (or a subset) and return
analysis-ready DataFrames. Title-agnostic: works for Anno 117 and Anno 1800.

DataFrame layer
---------------

.. automodule:: anno_save_analyzer.analysis.frames
   :members:
   :show-inheritance:

Deficit heatmap & Pareto
------------------------

.. automodule:: anno_save_analyzer.analysis.deficit
   :members:

Correlation
-----------

.. automodule:: anno_save_analyzer.analysis.correlation
   :members:

Route ranking
-------------

.. automodule:: anno_save_analyzer.analysis.routes
   :members:

Persistence (chronic / transient)
----------------------------------

.. automodule:: anno_save_analyzer.analysis.persistence
   :members:

Sensitivity (leave-one-out)
----------------------------

.. automodule:: anno_save_analyzer.analysis.sensitivity
   :members:

Forecast
--------

.. automodule:: anno_save_analyzer.analysis.forecast
   :members:

Decision Matrix — prescription engine
--------------------------------------

.. automodule:: anno_save_analyzer.analysis.prescribe
   :members:

Min-Cost Flow allocation
------------------------

.. automodule:: anno_save_analyzer.analysis.allocation
   :members:

OR-Tools VRP
------------

.. automodule:: anno_save_analyzer.analysis.optimize
   :members:
