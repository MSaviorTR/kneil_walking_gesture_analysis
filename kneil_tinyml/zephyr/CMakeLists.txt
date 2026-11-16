if(CONFIG_KNEIL_TINYML)
  set(KNEIL_DIR ${CMAKE_CURRENT_LIST_DIR}/..)
  zephyr_library_named(kneil_tinyml)
  zephyr_library_sources(
    ${KNEIL_DIR}/src/kneil_features.c
    ${KNEIL_DIR}/src/kneil_classifier.c
    ${KNEIL_DIR}/src/kneil_metrics.c
  )
  zephyr_library_sources_ifdef(CONFIG_KNEIL_TINYML_SELFTEST ${KNEIL_DIR}/src/kneil_selftest.c)
  zephyr_include_directories(${KNEIL_DIR}/include)
  # generated model code has an unused parameter in every tree function
  zephyr_library_compile_options(-Wno-unused-parameter)
endif()
