# Graph Report - .  (2026-07-12)

## Corpus Check
- Large corpus: 1307 files · ~1,201,301 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 3330 nodes · 6122 edges · 213 communities (166 shown, 47 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 635 edges (avg confidence: 0.72)
- Token cost: 269,825 input · 47,614 output

## Community Hubs (Navigation)
- Electron Bundle: Lodash Utils
- Web Profile Calibration
- Control Center: Chat/Approval Panels
- Control Center: Tab/Window Pickers
- Profile Health Monitoring
- Svintus Game Plugin Core
- Architecture Docs: Operator Contracts
- Perception Confidence & Evidence
- Control Center: Operator Panel
- Perception Service
- Windows Adapter: Control Selectors
- Control Center: Event Log
- Electron Bundle: Anchor/Parser Utils
- Control Center: Center Panel / HeroFrame
- State Replay Service
- Windows Adapter: Action Execution
- Session Orchestrator: DTOs
- Electron Bundle: fs-extra Copy
- Model Registry Service
- Control Center: Alerts & Escalation
- Session Orchestrator Entrypoints
- Electron Bundle: Auto-Updater
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 93
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 100
- Community 101
- Community 102
- Community 103
- Community 104
- Community 105
- Community 106
- Community 107
- Community 108
- Community 109
- Community 110
- Community 111
- Community 112
- Community 113
- Community 114
- Community 115
- Community 116
- Community 117
- Community 118
- Community 119
- Community 120
- Community 121
- Community 122
- Community 123
- Community 124
- Community 125
- Community 126
- Community 127
- Community 128
- Community 129
- Community 130
- Community 131
- Community 132
- Community 133
- Community 134
- Community 135
- Community 136
- Community 137
- Community 138
- Community 139
- Community 140
- Community 141
- Community 142
- Community 143
- Community 144
- Community 145
- Community 146
- Community 147
- Community 148
- Community 149
- Community 150
- Community 151
- Community 152
- Community 153
- Community 154
- Community 155
- Community 156
- Community 157
- Community 158
- Community 159
- Community 160
- Community 161
- Community 162
- Community 163
- Community 164
- Community 165
- Community 166
- Community 167
- Community 177
- Community 178
- Community 181
- Community 182
- Community 183
- Community 184
- Community 185
- Community 186
- Community 187
- Community 188
- Community 189
- Community 190
- Community 191
- Community 192
- Community 193
- Community 194
- Community 195
- Community 196
- Community 197
- Community 211
- Community 212

## God Nodes (most connected - your core abstractions)
1. `SessionOrchestrator` - 42 edges
2. `AppUpdater` - 33 edges
3. `ServiceClients` - 31 edges
4. `PlaywrightSession` - 30 edges
5. `emit()` - 26 edges
6. `write()` - 26 edges
7. `OperatorPanel()` - 26 edges
8. `InProcessClients` - 25 edges
9. `FlowController` - 22 edges
10. `App()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `SessionOrchestrator`  [INFERRED]
  scripts/orchestrator-debug.py → services/session-orchestrator/src/uno_orchestrator/orchestrator.py
- `main()` --calls--> `SessionOrchestrator`  [INFERRED]
  scripts/start-orchestrator-session-web.py → services/session-orchestrator/src/uno_orchestrator/orchestrator.py
- `main()` --calls--> `SessionOrchestrator`  [INFERRED]
  scripts/start-orchestrator-session-windows.py → services/session-orchestrator/src/uno_orchestrator/orchestrator.py
- `main()` --calls--> `run_benchmark()`  [INFERRED]
  scripts/benchmark-run.py → services/model-runtime-service/src/uno_model_runtime/benchmark_runner.py
- `main()` --calls--> `check_url_reachability()`  [INFERRED]
  scripts/check-web-reachability.py → services/adapter-web/src/uno_adapter_web/navigation_diagnostics.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Canonical Per-Tick Data Flow** — docs_architecture_intermediate_contract_observed_state, docs_architecture_intermediate_contract_inferred_state, docs_architecture_intermediate_contract_legal_actions, docs_architecture_intermediate_contract_decision_result, docs_architecture_intermediate_contract_execution_plan, docs_architecture_intermediate_contract_verified_result [EXTRACTED 1.00]
- **Per-Game Plugin Interface Set** — docs_architecture_plugin_interfaces_perception_plugin, docs_architecture_plugin_interfaces_rules_plugin, docs_architecture_plugin_interfaces_strategy_plugin, docs_architecture_plugin_interfaces_execution_plugin [EXTRACTED 0.90]
- **Model-Optional Task Routing** — docs_architecture_plugin_interfaces_game_model_config, docs_architecture_model_integration_resolve_model_profile, docs_architecture_overview_model_runtime_service, docs_architecture_model_integration_fallback_chain [EXTRACTED 0.85]
- **Autonomous perceive-decide-guard-execute-verify-record tick loop** — docs_runbooks_autonomous_windows_agent_run_windows_agent, docs_runbooks_autonomous_windows_agent_watchdog_windows_agent, docs_runbooks_autonomous_windows_agent_checkpoint_resume, docs_runbooks_autonomous_windows_agent_adaptive_backoff [EXTRACTED 1.00]
- **Screenshot trace capture and display flow** — docs_runbooks_screenshot_trace_playwright_session, docs_runbooks_screenshot_trace_trace_manager, docs_runbooks_screenshot_trace_trace_panel [EXTRACTED 1.00]
- **Selector health monitoring and drift alerting** — docs_runbooks_real_unoh_web_profile_selector_health, docs_runbooks_real_unoh_web_profile_nightly_profile_smoke, docs_runbooks_real_unoh_web_profile_no_silent_healing [EXTRACTED 1.00]
- **Perception → decision → action operator loop** — services_session_orchestrator_readme_session_orchestrator, services_perception_service_readme_perception_service, services_decision_service_readme_decision_service, services_policy_guard_readme_policy_guard [INFERRED 0.75]
- **Model inference stack** — services_model_registry_service_readme_model_registry_service, services_model_runtime_service_readme_model_runtime_service, services_decision_service_readme_decision_service, services_chat_response_service_readme_chat_response_service [INFERRED 0.75]
- **Adapters feed evidence to perception** — services_adapter_web_readme_adapter_web, services_adapter_windows_readme_adapter_windows, services_perception_service_readme_perception_service [INFERRED 0.75]
- **Agent run 6d158176 UNO session sequence (observe frames + screenshots + failure)** — services_artifacts_6d158176_87be_4160_b3c6_c559635908cc_001_observe_frame_frame, services_artifacts_6d158176_87be_4160_b3c6_c559635908cc_002_observe_frame_frame, services_artifacts_6d158176_87be_4160_b3c6_c559635908cc_screenshot_1782284303324, services_artifacts_6d158176_87be_4160_b3c6_c559635908cc_screenshot_1782284316022, services_artifacts_6d158176_87be_4160_b3c6_c559635908cc_failure_1782284316386 [INFERRED 0.75]
- **Agent run ceb134ab UNO session sequence (observe frames + failure)** — services_artifacts_ceb134ab_226d_4ada_b357_a51660bfdb33_001_observe_frame_frame, services_artifacts_ceb134ab_226d_4ada_b357_a51660bfdb33_002_observe_frame_frame, services_artifacts_ceb134ab_226d_4ada_b357_a51660bfdb33_failure_1782284507760 [INFERRED 0.75]
- **ceb134ab agent run — PIZZUNO +4 Wild session** — services_artifacts_ceb134ab_226d_4ada_b357_a51660bfdb33_screenshot_1782284495907_screenshot, services_artifacts_ceb134ab_226d_4ada_b357_a51660bfdb33_screenshot_1782284507295_screenshot [INFERRED 0.75]
- **e1e86e5e agent run — PIZZUNO session ending in failure** — services_artifacts_e1e86e5e_3f32_4091_82ed_d8f1a335dcc8_001_observe_frame_frame, services_artifacts_e1e86e5e_3f32_4091_82ed_d8f1a335dcc8_002_observe_frame_frame, services_artifacts_e1e86e5e_3f32_4091_82ed_d8f1a335dcc8_screenshot_1782285804342_screenshot, services_artifacts_e1e86e5e_3f32_4091_82ed_d8f1a335dcc8_screenshot_1782285811147_screenshot, services_artifacts_e1e86e5e_3f32_4091_82ed_d8f1a335dcc8_failure_1782285811429_failure [INFERRED 0.75]
- **e2e-full agent run session (UNO bot-turn screenshots)** — services_artifacts_e2e_full_screenshot_1782284216799, services_artifacts_e2e_full_screenshot_1782284265921, services_artifacts_e2e_full_screenshot_1782284459511, services_artifacts_e2e_full_screenshot_1782285774571 [INFERRED 0.75]
- **e2e-pw Playwright observe run session (UNO frames)** — services_artifacts_e2e_pw_001_observe_frame, services_artifacts_e2e_pw_screenshot_1782284211002, services_artifacts_e2e_pw_screenshot_1782284260221, services_artifacts_e2e_pw_screenshot_1782284453959 [INFERRED 0.75]
- **smoke-selectors agent run: sequence of Pizzuno board observations** — services_artifacts_smoke_selectors_001_observe_frame, services_artifacts_smoke_selectors_screenshot_1782284334730, services_artifacts_smoke_selectors_screenshot_1782284526566, services_artifacts_smoke_selectors_screenshot_1782285832270, services_artifacts_smoke_selectors_screenshot_1782804024540 [INFERRED 0.75]

## Communities (213 total, 47 thin omitted)

### Community 0 - "Electron Bundle: Lodash Utils"
Cohesion: 0.01
Nodes (82): baseToString(), byte2hex, clearBuffers(), Comparator, Comparator$1, Comparator$2, compareIdentifiers$1(), compileStyleMap() (+74 more)

### Community 1 - "Web Profile Calibration"
Cohesion: 0.05
Nodes (63): calibrate_from_file(), capture_live_screenshot(), main(), Image, Calibrate scuffed-uno-web profile from live screenshot.  Usage:     python scrip, Capture a screenshot from a live Chrome CDP session., Load a screenshot from file., analyze_screenshot() (+55 more)

### Community 2 - "Control Center: Chat/Approval Panels"
Cohesion: 0.06
Nodes (51): ApprovalPanel(), Props, Props, Props, MODE_LABELS, Props, ASSIST_PATTERNS, CommandResult (+43 more)

### Community 3 - "Control Center: Tab/Window Pickers"
Cohesion: 0.06
Nodes (46): BrowserTabPicker(), filterTabs(), isTabCompatible(), Props, filterCandidates(), GameWindowPicker(), Props, sortCandidates() (+38 more)

### Community 4 - "Profile Health Monitoring"
Cohesion: 0.08
Nodes (48): ProfileHealthConfig, ProfileHealthRemediation, ProfileHealthStatus, main(), main(), main(), load_ctx(), main() (+40 more)

### Community 5 - "Svintus Game Plugin Core"
Cohesion: 0.08
Nodes (31): _dict_to_game_action(), _game_action_to_dict(), Any, GameAction, GameEvent, GameSnapshot, Svintus game plugin — second GamePlugin implementation.  Demonstrates that the G, Svintus game plugin implementing the GamePlugin protocol.      Key differences f (+23 more)

### Community 6 - "Architecture Docs: Operator Contracts"
Cohesion: 0.06
Nodes (50): Windows Operator Client (Control Center), Benchmark Pipeline, Bounded Context Map (superseded), Full-Operator Evaluation, Affordances (reconciled), DecisionResult, Entity, ExecutionPlan (+42 more)

### Community 7 - "Perception Confidence & Evidence"
Cohesion: 0.04
Nodes (48): Perception Confidence Metadata, DomEvidence, perception-service, adapter-web, DomSnapshot, WebAdapterProfile, adapter-windows, clients.py (+40 more)

### Community 8 - "Control Center: Operator Panel"
Cohesion: 0.11
Nodes (42): App(), executeCommand(), explainError(), FLOW_STATE_CLASS, getRecoveryHint(), mergeSession(), OperatorPanel(), PanelState (+34 more)

### Community 9 - "Perception Service"
Cohesion: 0.08
Nodes (36): ObservationDiscrepancy, OcrEvidence, merge(), perceive(), PerceptionRequest, BaseModel, Observation, build_observation() (+28 more)

### Community 10 - "Windows Adapter: Control Selectors"
Cohesion: 0.09
Nodes (42): ControlSelector, capture_screenshot(), compute_diff(), get_bounds(), get_calibration(), get_window_title(), main(), Path (+34 more)

### Community 11 - "Control Center: Event Log"
Cohesion: 0.07
Nodes (24): Props, STEP_COLORS, EvidenceData, EvidencePanel(), formatConfidence(), formatTimestamp(), Props, FLOW_COLORS (+16 more)

### Community 12 - "Electron Bundle: Anchor/Parser Utils"
Cohesion: 0.12
Nodes (42): beginAnchorTransaction(), captureSegment(), charFromCodepoint(), _class(), commitAnchorTransaction(), composeNode(), escapedHexLen(), fromDecimalCode() (+34 more)

### Community 13 - "Control Center: Center Panel / HeroFrame"
Cohesion: 0.08
Nodes (29): CenterPanel(), Props, buildTraceSrc(), HeroFrame(), Props, HeroImage(), Props, Props (+21 more)

### Community 14 - "State Replay Service"
Cohesion: 0.08
Nodes (18): ReplayDetail, ReplaySummary, append_artifact(), append_event(), append_observation(), get_replay(), import_replay(), DomainEvent (+10 more)

### Community 15 - "Windows Adapter: Action Execution"
Cohesion: 0.07
Nodes (34): attach(), capture_fixture(), execute_action(), get_calibration(), get_evidence(), get_learned_zones(), get_profile(), get_profiles() (+26 more)

### Community 16 - "Session Orchestrator: DTOs"
Cohesion: 0.05
Nodes (22): ActionExecutionRequest, ActionExecutionResult, AdapterEvidenceBundle, Any, AttachWindowsAdapterRequest, AttachWindowsAdapterResponse, ChatIntent, ChatReply (+14 more)

### Community 17 - "Electron Bundle: fs-extra Copy"
Cohesion: 0.07
Nodes (41): areIdentical$2(), checkParentDir(), checkParentPaths(), checkParentPathsSync(), checkPaths(), checkPathsSync(), copy$2(), copyDir() (+33 more)

### Community 18 - "Model Registry Service"
Cohesion: 0.07
Nodes (24): activate(), disable_profile(), get_model(), get_profile(), install(), list_models(), list_profiles(), BaseModel (+16 more)

### Community 19 - "Control Center: Alerts & Escalation"
Cohesion: 0.09
Nodes (23): Alert, AlertBar(), Props, EscalationPanel(), formatTime(), Props, SEVERITY_CONFIG, Decision (+15 more)

### Community 20 - "Session Orchestrator Entrypoints"
Cohesion: 0.07
Nodes (26): main(), main(), main(), build_verification(), classify_action_category(), classify_screen_state(), derive_expected_outcome_profile(), derive_goal() (+18 more)

### Community 21 - "Electron Bundle: Auto-Updater"
Cohesion: 0.08
Nodes (33): addUpdaterMenu(), buildMenu(), checkForCrashOnStartup(), checkForUpdates(), createFileSync$1(), createWindow(), ensureLogDir(), exportDiagnostics() (+25 more)

### Community 22 - "Community 22"
Cohesion: 0.11
Nodes (22): Final verification verdict., VerificationResult, humanized_move_and_click(), press_keys(), Humanized mouse/keyboard input within window bounds., type_text(), clamp_point_to_bounds(), ensure_focus() (+14 more)

### Community 23 - "Community 23"
Cohesion: 0.09
Nodes (25): browser_launch_mode(), browser_launch_options(), format_startup_error(), format_startup_failure(), goto_timeout_ms(), goto_wait_until(), PlaywrightStartupError, Any (+17 more)

### Community 24 - "Community 24"
Cohesion: 0.08
Nodes (33): Control Center, session-orchestrator, Starting a Session, Web adapter profiles (local-mock-uno, real-unoh-web), Win32 EnumWindows window picker, HeuristicCanvasUNOPlugin, scuffed-uno-web profile, Canvas games need web adapter, not windows adapter (+25 more)

### Community 25 - "Community 25"
Cohesion: 0.08
Nodes (21): GameState, AlertStack(), Props, SEVERITY_CONFIG, ConfidenceMeter(), Props, DirectionIndicator(), Props (+13 more)

### Community 26 - "Community 26"
Cohesion: 0.08
Nodes (31): blockHeader(), chooseScalarStyle(), codePointAt(), DEPRECATED_BOOLEANS_SYNTAX, detectType(), dropEndingNewline(), dump(), encodeHex() (+23 more)

### Community 27 - "Community 27"
Cohesion: 0.07
Nodes (27): capture_fixture(), check_cdp_port(), execute_action(), get_evidence(), get_latest_trace_frame(), get_latest_trace_meta(), get_screenshot(), get_trace_file() (+19 more)

### Community 28 - "Community 28"
Cohesion: 0.12
Nodes (26): decide_action(), DecisionRequest, DecisionResult, decide(), decide_heuristic(), decide_model(), decide_random(), _format_actions_for_prompt() (+18 more)

### Community 29 - "Community 29"
Cohesion: 0.13
Nodes (12): FlowState, RuntimeSession, FlowControlResponse, SessionConfig, SessionSpec, SessionState, SessionOrchestrator, can_transition() (+4 more)

### Community 30 - "Community 30"
Cohesion: 0.12
Nodes (15): FlowStepName, FlowController, AdapterBinding, DecisionResult, DomEvidence, ErrorClass, LegalAction, Observation (+7 more)

### Community 31 - "Community 31"
Cohesion: 0.14
Nodes (17): Any, Path, Lightweight screenshot trace manager for agent pipeline debugging.  Feature-flag, Trace perceive phase: save observation metadata., Trace execute phase: save before screenshot and action metadata., Trace execute phase: save after screenshot with stabilization delay., Capture viewport screenshot. Returns path or None on failure., Trace observe phase: save the exact screenshot used for CV. (+9 more)

### Community 32 - "Community 32"
Cohesion: 0.10
Nodes (18): capture(), main(), Path, attach(), AttachWebAdapterRequest, AttachWebAdapterResponse, attach_adapter(), create_adapter() (+10 more)

### Community 33 - "Community 33"
Cohesion: 0.13
Nodes (19): callback(), Diagnose exactly why UNO is dropped in _list_win32 callback., browser_candidate_warning(), is_browser_host(), UiNodeSnapshot, Browser host attach ambiguity detection., Return (warning, detail) when selected title and active document diverge., title_core() (+11 more)

### Community 34 - "Community 34"
Cohesion: 0.14
Nodes (13): compare_grounding(), evidence_summary(), Any, Post-action verification — action-aware evidence comparison.  Compares before/af, Produce a verification verdict for an executed action.    Verdicts:   - confirme, Collected evidence before and after an action., Compare before/after ActionGrounding to detect changes., Produce a human-readable evidence summary for validation reports. (+5 more)

### Community 35 - "Community 35"
Cohesion: 0.09
Nodes (23): attach_adapter(), create_session(), create_session_legacy(), detach_adapter(), get_session(), pause_session(), AdapterType, AttachAdapterBody (+15 more)

### Community 36 - "Community 36"
Cohesion: 0.14
Nodes (26): attrib(), beginWhiteSpace(), charAt(), checkBufferLength(), closeTag(), closeText(), constructYamlBinary(), emitNode() (+18 more)

### Community 37 - "Community 37"
Cohesion: 0.10
Nodes (18): DomSnapshot, build_extracted_snapshot(), dom_snapshot_to_evidence(), _find_node(), normalize_playwright_nodes(), _parse_card_from_element(), DomEvidence, DomNodeEvidence (+10 more)

### Community 39 - "Community 39"
Cohesion: 0.11
Nodes (16): FLOW_COLORS, FLOW_LABELS, FlowStateBadge(), Props, Props, ModeSwitcher(), Props, PHASE_LABELS (+8 more)

### Community 40 - "Community 40"
Cohesion: 0.11
Nodes (10): PlaywrightSession, Any, DomNodeEvidence, Path, WebAdapterProfile, WebPageDiagnostics, WebStartupDiagnostics, Post-attach validation: verify the page matches profile domain. (+2 more)

### Community 41 - "Community 41"
Cohesion: 0.10
Nodes (20): arrayPush(), arraySome(), baseGetAllKeys(), baseIsEqualDeep(), buildBlockFileMap(), buildChecksumMap(), cacheHas(), computeOperations() (+12 more)

### Community 42 - "Community 42"
Cohesion: 0.13
Nodes (16): NetworkReachabilityCheck, PageGotoDiagnostics, main(), Check whether a target URL is reachable outside Playwright., network_check(), _as_int(), _as_str(), check_url_reachability() (+8 more)

### Community 43 - "Community 43"
Cohesion: 0.14
Nodes (21): PublicTableState, apply_game_action(), ApplyActionRequest, ApplyActionResponse, create_game(), export_replay(), get_events(), _get_game() (+13 more)

### Community 44 - "Community 44"
Cohesion: 0.10
Nodes (23): arrayLikeKeys(), baseGetTag(), baseIsArguments(), baseIsEqual(), baseIsNative(), baseIsTypedArray(), baseKeys(), baseTimes() (+15 more)

### Community 45 - "Community 45"
Cohesion: 0.09
Nodes (19): assign(), assignKey(), baseUnary(), compileStyleAliases(), deepAssign(), handleError(), isObject$1(), isOldWin6() (+11 more)

### Community 46 - "Community 46"
Cohesion: 0.12
Nodes (19): ChatPolicyResult, PolicyViolation, guard_chat(), guard_decision(), GuardDecisionRequest, GuardDecisionResponse, BaseModel, ChatReply (+11 more)

### Community 47 - "Community 47"
Cohesion: 0.13
Nodes (21): Popen, Visual RPA execution pipeline: locate -> act -> verify., _capture_via_printwindow(), capture_window_screenshot(), _connect_handle(), connect_window_by_handle(), extract_ui_tree(), find_window() (+13 more)

### Community 48 - "Community 48"
Cohesion: 0.20
Nodes (21): analyze_uia_tree(), browser_match_card_message(), _control_type(), _document_depth(), is_actionable_node(), missing_target_message(), page_nodes(), UiNodeSnapshot (+13 more)

### Community 49 - "Community 49"
Cohesion: 0.18
Nodes (12): _game_action_to_legal_action(), _legal_action_to_game_action(), Any, GameAction, GameEvent, GameSnapshot, GameState, UNO game plugin — first GamePlugin implementation.  Wraps the existing uno-core (+4 more)

### Community 50 - "Community 50"
Cohesion: 0.15
Nodes (18): KeyboardHandlers, useKeyboardShortcuts(), extractDecision(), extractGameState(), extractVerification(), SERVICE_PORTS, useOperatorPolling(), useStaleDetection() (+10 more)

### Community 51 - "Community 51"
Cohesion: 0.12
Nodes (18): get_profile(), get_profile_compatibility(), get_profiles(), playwright_check(), WebAdapterProfile, Return domain compatibility info for a web profile., list_profiles(), load_profile() (+10 more)

### Community 52 - "Community 52"
Cohesion: 0.15
Nodes (13): GestureConfidence, GesturePlan, GestureTarget, GestureType, get_profile_gesture_hints(), plan_gesture(), Any, StrEnum (+5 more)

### Community 53 - "Community 53"
Cohesion: 0.10
Nodes (21): devDependencies, electron, electron-builder, @types/react, @types/react-dom, typescript, vite, vite-plugin-electron (+13 more)

### Community 54 - "Community 54"
Cohesion: 0.14
Nodes (12): convert_cv_to_css(), convert_draw_pile_css(), coordinate_to_dict(), CoordinateConversion, Any, Coordinate-space reliability — explicit transformations, validation, and logging, Serialize conversion chain to metadata dict., Records the full coordinate transformation chain. (+4 more)

### Community 55 - "Community 55"
Cohesion: 0.14
Nodes (20): analyze_crop_colors(), CardRecognitionResult, _classify_pixel_color_hsv(), _detect_card_number(), _detect_special_card(), Any, Image, Card identity recognizer — structured extraction from crops.  Takes cropped card (+12 more)

### Community 56 - "Community 56"
Cohesion: 0.19
Nodes (9): configureRequestOptions(), configureRequestOptionsFromUrl(), configureRequestUrl(), createHttpError(), debug$2, hashSensitiveValue(), HttpExecutor, parseUrl() (+1 more)

### Community 57 - "Community 57"
Cohesion: 0.14
Nodes (4): DifferentialDownloader, GenericDifferentialDownloader, ProgressDifferentialDownloadCallbackTransform, removeQuery()

### Community 58 - "Community 58"
Cohesion: 0.16
Nodes (18): action_requires_canvas_click(), build_coordinate_click_payload(), click_point_from_canvas(), diagnose_page(), is_canvas_profile(), ActionExecutionRequest, WebAdapterProfile, WebPageDiagnostics (+10 more)

### Community 59 - "Community 59"
Cohesion: 0.12
Nodes (10): MockWindowsAdapter, WindowsActionExecutionRequest, WindowsActionExecutionResult, WindowsAdapterMode, WindowsEvidenceBundle, build_mock_synthetic_frame(), Path, ScreenFrame (+2 more)

### Community 60 - "Community 60"
Cohesion: 0.11
Nodes (8): AdapterRetryPolicy, GenericActionRequest, GenericActionResult, GenericAttachRequest, GenericAttachResponse, GenericEvidenceBundle, InProcessAdapterClient, In-process adapter client using ASGI transport.

### Community 61 - "Community 61"
Cohesion: 0.16
Nodes (5): DownloadedUpdateHelper, Hash(), ListCache(), MapCache(), NoOpLogger

### Community 62 - "Community 62"
Cohesion: 0.16
Nodes (15): load(), PreviewFrameDisplay, PreviewFrameKind, resolvePreviewFrameKind(), resolveWindowsPreviewDisplay(), base, checkServiceHealth(), getWindowsRpaPreview() (+7 more)

### Community 63 - "Community 63"
Cohesion: 0.16
Nodes (15): RecoveryConfig, LowConfidenceError, Exception, End-to-end perceive → decide → guard → execute loop., Get the retry/recovery policy for an adapter type from the registry., classify_attach_error(), classify_error(), decide_recovery() (+7 more)

### Community 64 - "Community 64"
Cohesion: 0.19
Nodes (14): _attach_and_start(), _build_orchestrator(), main(), _metrics_snapshot(), _now_ms(), parse_args(), Namespace, Path (+6 more)

### Community 65 - "Community 65"
Cohesion: 0.12
Nodes (9): WindowsAdapterProfile, Path, WindowsAdapterProfile, Get client area bounds (content-only, excluding title bar / borders)., ScreenFrame, VisualActionResult, In-memory operator preview and action history., RpaSessionState (+1 more)

### Community 66 - "Community 66"
Cohesion: 0.16
Nodes (15): detect(), IntentRequest, BaseModel, ChatIntent, detect_intent(), detect_intent_model(), detect_intent_rules(), detect_intent_sync() (+7 more)

### Community 67 - "Community 67"
Cohesion: 0.16
Nodes (15): CardRecognition, Result of recognizing a single card from a crop., crop_region(), extract_from_screenshot(), UNO visual extraction schema and card recognizer.  Structured schema for extract, Map CardRecognition to VisualCard., Convenience function for extraction., A single detected card from screenshot. (+7 more)

### Community 68 - "Community 68"
Cohesion: 0.16
Nodes (3): InProcessClients, ActionExecutionRequest, AttachWebAdapterRequest

### Community 69 - "Community 69"
Cohesion: 0.25
Nodes (16): logWarn(), createWindow(), loadWindowContent(), SERVICES, waitForUrl(), DEFAULT_SETTINGS, getCrashFiles(), getSettingsPath() (+8 more)

### Community 70 - "Community 70"
Cohesion: 0.18
Nodes (14): ChatReply, ChatReplyRequest, reply(), _check_safety(), generate_reply(), generate_reply_model(), generate_reply_template(), ChatReply (+6 more)

### Community 71 - "Community 71"
Cohesion: 0.12
Nodes (13): binding_for(), AdapterBinding, AdapterType, AttachWebAdapterRequest, AttachWebAdapterResponse, HTTP clients for downstream services., _url(), OrchestratorStatus (+5 more)

### Community 73 - "Community 73"
Cohesion: 0.15
Nodes (17): copyFile(), copyFile$1(), fileIsNotWritable(), fileIsNotWritable$1(), handleTimestamps(), handleTimestampsAndMode(), makeFileWritable(), makeFileWritable$1() (+9 more)

### Community 74 - "Community 74"
Cohesion: 0.19
Nodes (13): main(), invoke_with_fallback(), ModelInvocationRequest, ModelInvocationResponse, ModelProfile, Invocation orchestration with safe fallback to mock., get_provider(), MockProvider (+5 more)

### Community 75 - "Community 75"
Cohesion: 0.12
Nodes (7): PlaywrightWebAdapter, ActionExecutionRequest, ActionExecutionResult, AdapterEvidenceBundle, AdapterMode, WebAdapterProfile, Playwright-backed web adapter session wrapper.

### Community 76 - "Community 76"
Cohesion: 0.15
Nodes (13): _color_region_avg(), _estimate_image_size(), HeuristicCanvasUNOPlugin, _is_likely_empty_region(), Heuristic canvas perception plugin for UNO.  Uses profile-guided zones + color/s, Get image dimensions without PIL dependency., Get zone definitions from profile or defaults., Get average color of a region. Returns {r, g, b, brightness}. (+5 more)

### Community 77 - "Community 77"
Cohesion: 0.24
Nodes (11): RuntimeAdapter, get_runtime(), LlamaCppRuntime, MockRuntime, ABC, InferenceRequest, InferenceResponse, Unified inference interface with pluggable runtime adapters. (+3 more)

### Community 78 - "Community 78"
Cohesion: 0.14
Nodes (6): WindowsActionExecutionRequest, WindowsActionExecutionResult, WindowsAdapterMode, WindowsEvidenceBundle, PywinautoWindowsAdapter, Pywinauto-backed visual attended RPA adapter.

### Community 79 - "Community 79"
Cohesion: 0.19
Nodes (6): FileWithEmbeddedBlockMapDifferentialDownloader, newUrlFromBase(), NsisUpdater, readBlockMap(), readEmbeddedBlockMapData(), stripBom$1()

### Community 80 - "Community 80"
Cohesion: 0.23
Nodes (10): checkIsRangesSupported(), checkSha2(), configurePipes(), copyData(), doExecuteTasks(), end(), executeTasksUsingMultipleRangeRequests(), getNetSession() (+2 more)

### Community 81 - "Community 81"
Cohesion: 0.21
Nodes (13): logError(), buildMenu(), addUpdaterMenu(), checkForUpdates(), exportDiagnostics(), installUpdate(), notifyRenderer(), setupUpdater() (+5 more)

### Community 82 - "Community 82"
Cohesion: 0.13
Nodes (14): author, dependencies, electron-updater, react, react-dom, description, license, main (+6 more)

### Community 83 - "Community 83"
Cohesion: 0.19
Nodes (12): BenchmarkRunRequest, benchmark_run(), invoke(), _load_profile(), provider_health(), BenchmarkResult, ModelInvocationRequest, ModelInvocationResponse (+4 more)

### Community 86 - "Community 86"
Cohesion: 0.19
Nodes (13): PromptResolution, get_prompts(), PromptProfile, status(), _extract_vars(), list_prompts(), _prompts_root(), ModelUseCase (+5 more)

### Community 87 - "Community 87"
Cohesion: 0.21
Nodes (10): Deck construction and shuffling., shuffle_deck(), apply_action(), _apply_card_effect(), DomainEvent, GameState, LegalAction, Apply actions and emit domain events. (+2 more)

### Community 89 - "Community 89"
Cohesion: 0.15
Nodes (3): ElectronAppAdapter, requireComparator(), requireRange()

### Community 90 - "Community 90"
Cohesion: 0.15
Nodes (13): build, appId, directories, files, productName, publish, output, owner (+5 more)

### Community 91 - "Community 91"
Cohesion: 0.28
Nodes (7): RecoveryDecision, AdapterBinding, AdapterType, AttachAdapterBody, RuntimeError, WebAttachFailedError, decide_attach_recovery()

### Community 92 - "Community 92"
Cohesion: 0.22
Nodes (11): PageLike, probe_selector(), Any, ProfileSelector, Protocol, SelectorCheckResult, Explicit selector chain resolution with observability., Sync resolution for extracted DomNodeEvidence list (extraction path). (+3 more)

### Community 93 - "Community 93"
Cohesion: 0.28
Nodes (13): e2e-full screenshot: UNO Mock Test Target (bot turn), e2e-full screenshot: UNO Mock Test Target (bot turn), e2e-full screenshot: UNO Mock Test Target (bot turn), e2e-full screenshot: UNO Mock Test Target (bot turn), UNO actions panel (Draw, Play Red 5), UNO chat panel (Player2 asks rules), UNO discard pile (Red 5, draw pile 80), UNO hand panel (Red 5, Blue 3, Yellow Skip) (+5 more)

### Community 94 - "Community 94"
Cohesion: 0.26
Nodes (6): _parse_structured(), ModelInvocationRequest, ModelInvocationResponse, ModelProfile, ModelProviderHealth, StructuredModelOutput

### Community 96 - "Community 96"
Cohesion: 0.32
Nodes (5): computeReleaseNotes(), getNoteValue(), isNameEquals(), parseXml(), XElement

### Community 97 - "Community 97"
Cohesion: 0.32
Nodes (3): createTempUpdateFile(), doLoadAutoUpdater(), MacUpdater

### Community 99 - "Community 99"
Cohesion: 0.17
Nodes (12): compilerOptions, jsx, lib, module, moduleResolution, outDir, skipLibCheck, strict (+4 more)

### Community 100 - "Community 100"
Cohesion: 0.20
Nodes (5): CardColor, PlayerRef, create_initial_state(), GameState, Internal canonical game state — not exposed as observation truth.

### Community 101 - "Community 101"
Cohesion: 0.29
Nodes (12): Player Card Hand, Discard Pile, Agent Run Failure State, UNO (PIZZUN) Game Board, UNO (PIZZUN) board observe frame 001 - purple 2 discard, hand 9/Reverse/0/7/8/9, UNO (PIZZUN) board observe frame 002 - purple 2 discard, hand 9/Reverse/0/7/8/9, UNO (PIZZUN) failure screenshot - board with purple 2 discard, hand 9/Reverse/0/7/8/9, UNO (PIZZUN) run screenshot 303324 - board with purple 2 discard, hand 9/Reverse/0/7/8/9 (+4 more)

### Community 102 - "Community 102"
Cohesion: 0.24
Nodes (5): Validate that a click target is within reasonable bounds.    Returns (is_valid,, validate_click_target(), ActionExecutionRequest, ActionExecutionResult, TestValidateClickTarget

### Community 103 - "Community 103"
Cohesion: 0.31
Nodes (10): ensureLogDir(), getLogDir(), getLogFile(), log(), LOG_DIR, logDebug(), LogEntry, LogLevel (+2 more)

### Community 104 - "Community 104"
Cohesion: 0.18
Nodes (11): nsis, allowToChangeInstallationDirectory, createDesktopShortcut, createStartMenuShortcut, deleteAppDataOnUninstall, installerHeaderIcon, installerIcon, oneClick (+3 more)

### Community 105 - "Community 105"
Cohesion: 0.25
Nodes (8): ANALYTICS_EVENTS, _analyticsBuffer, AnalyticsEvent, logActionExecuted(), logAnalyticsEvent(), logConfidence(), logEscalation(), logModeChange()

### Community 106 - "Community 106"
Cohesion: 0.27
Nodes (11): Agent run failure state, PIZZUNO game board UI, UNO Mock Test Target UI, PIZZUNO board — +4 Wild discard, hand 7/8/4/Skip/9/8, PIZZUNO board — +4 Wild discard (identical state), PIZZUNO board — yellow 9 discard, hand 2/9/0/Reverse/3/Reverse, PIZZUNO board observe frame 2 (yellow 9 discard), Agent run failure — PIZZUNO board (yellow 9 discard) (+3 more)

### Community 107 - "Community 107"
Cohesion: 0.33
Nodes (3): determineBufferEncoding(), emit(), SAXStream()

### Community 108 - "Community 108"
Cohesion: 0.20
Nodes (10): assocIndexOf(), eq2(), higherGT(), listCacheDelete(), listCacheGet(), listCacheHas(), listCacheSet(), lowerLT() (+2 more)

### Community 111 - "Community 111"
Cohesion: 0.29
Nodes (10): defaults(), fixWinEPERM(), fixWinEPERMSync(), rimraf_(), rimraf$1(), rimrafSync(), rmdir(), rmdirSync() (+2 more)

### Community 112 - "Community 112"
Cohesion: 0.29
Nodes (8): BenchmarkCase, main(), load_dataset(), BenchmarkResult, ModelProfile, Benchmark dataset loader and runner., run_benchmark(), _score_case()

### Community 113 - "Community 113"
Cohesion: 0.20
Nodes (10): benchmark_runner.py, Model Runtime, prompts_registry.py, providers.py, llama.cpp server, Model Provider Setup, vLLM, PromptProfile (+2 more)

### Community 114 - "Community 114"
Cohesion: 0.29
Nodes (8): OperatorEvaluationRun, OperatorScenario, OperatorScenarioResult, main(), load_operator_dataset(), Full-operator evaluation runner., run_operator_evaluation(), _score_scenario()

### Community 115 - "Community 115"
Cohesion: 0.24
Nodes (8): main(), run_e2e_trace(), trace_step(), In-process HTTP clients for tests and local evaluation (ASGI transport)., Register in-process adapter clients for testing., Register the adapter-windows service as an in-process (ASGI) client.      Routes, setup_in_process_adapter_registry(), setup_in_process_windows_registry()

### Community 116 - "Community 116"
Cohesion: 0.20
Nodes (5): Protocol, WindowsActionExecutionRequest, WindowsActionExecutionResult, WindowsEvidenceBundle, WindowsAdapterSession

### Community 117 - "Community 117"
Cohesion: 0.29
Nodes (10): E2E-PW: UNO Mock Test Target page, UNO Mock Test Target minimal HTML harness, Smoke: Pizzuno board, discard red 1 (JOHNCENNA321), Discard pile top card, Pizzuno multiplayer UNO game board UI, Player hand of playable cards, Smoke: Pizzuno board, discard red 6 (RICARDOFIORANI hand), Smoke: Pizzuno board, discard yellow Skip (AI3000 hand) (+2 more)

### Community 118 - "Community 118"
Cohesion: 0.29
Nodes (7): AppConfig, FeatureFlags, get_config(), get_features(), load_config(), BaseModel, Path

### Community 119 - "Community 119"
Cohesion: 0.28
Nodes (4): getVariant(), stringify(), UUID, uuidNamed()

### Community 120 - "Community 120"
Cohesion: 0.25
Nodes (9): compare(), compare$b(), compareBuild(), compareBuild$3(), compareMain(), comparePre(), diff$1(), maxSatisfying$1() (+1 more)

### Community 121 - "Community 121"
Cohesion: 0.22
Nodes (6): electron, fs, path, include, electron, src

### Community 122 - "Community 122"
Cohesion: 0.31
Nodes (8): AgentPlan, AgentScreenState, ExecutionTraceStep, formatTime(), PHASE_ICONS, Props, STATE_ICONS, StrategyPanel()

### Community 123 - "Community 123"
Cohesion: 0.25
Nodes (7): Protocol, Screenshot perception plugin protocol.  Generic interface for plugins that extra, Result of screenshot-based perception., Protocol for screenshot-based perception plugins., Infer game state from a screenshot file.          Args:             screenshot_p, ScreenshotInference, ScreenshotPerceptionPlugin

### Community 124 - "Community 124"
Cohesion: 0.33
Nodes (8): _empty_state(), infer_from_screenshot(), _normalize_vlm_output(), Any, VLM perception provider — screenshot-based inference for canvas/WebGL games.  Ta, Return empty state when VLM fails., Call VLM to infer game state from screenshot.          Returns a dict compatible, Normalize VLM output into canonical InferredState format.

### Community 125 - "Community 125"
Cohesion: 0.50
Nodes (8): _can_play_on_top(), generate_legal_actions(), is_action_legal(), _match_action(), GameState, LegalAction, Legal action generation and validation., validate_action()

### Community 126 - "Community 126"
Cohesion: 0.39
Nodes (6): checkForCrashOnStartup(), CrashInfo, getCrashInfo(), setupCrashReporting(), logInfo(), saveCrashState()

### Community 127 - "Community 127"
Cohesion: 0.25
Nodes (8): scripts, build, build:dir, build:win, dev, postinstall, preview, test

### Community 128 - "Community 128"
Cohesion: 0.39
Nodes (7): capture_screenshot(), get_calibration(), get_current_ratios(), main(), Path, Assisted calibration for real-uno-desktop layout_targets.  Screenshot is client-, update_profile()

### Community 129 - "Community 129"
Cohesion: 0.32
Nodes (5): get_logs(), ingest_log(), LogEntry, metrics(), BaseModel

### Community 130 - "Community 130"
Cohesion: 0.36
Nodes (7): _classify_color(), _detect_extent(), HandCardSlot, Segment the player's hand strip into individual cards.  Calibrated against real, Find [x_start, x_end] of the bright card strip inside the region., Segment the hand region (absolute px {x,y,width,height}) into card slots., segment_hand_cards()

### Community 132 - "Community 132"
Cohesion: 0.29
Nodes (7): addSensitiveFieldPattern(), addSensitiveRedirectHeader(), isSensitiveFieldName(), normalizeName(), SENSITIVE_FIELD_PATTERNS, SENSITIVE_FIELD_SUFFIXES, SENSITIVE_REDIRECT_HEADERS

### Community 133 - "Community 133"
Cohesion: 0.29
Nodes (7): close(), closeSync(), enqueue(), resetQueue(), retry$2(), utimesMillis$1(), utimesMillisSync$1()

### Community 134 - "Community 134"
Cohesion: 0.38
Nodes (6): AgentTransparencyPanel(), getConfidenceBar(), Props, STATE_CONFIG, AgentState, AgentTransparency

### Community 135 - "Community 135"
Cohesion: 0.38
Nodes (3): main(), MockUnoApp, Deterministic tkinter test target for adapter-windows real-mode tests.  Draw but

### Community 136 - "Community 136"
Cohesion: 0.38
Nodes (6): load_replay(), DomainEvent, GameState, ReplayEnvelope, Replay events back into state., replay_events()

### Community 138 - "Community 138"
Cohesion: 0.33
Nodes (6): constructor(), format(), formatBytes(), inc(), inc$1(), minVersion$1()

### Community 141 - "Community 141"
Cohesion: 0.33
Nodes (5): requireBrowser(), requireCommon(), requireHasFlag(), requireNode(), requireSupportsColor()

### Community 142 - "Community 142"
Cohesion: 0.33
Nodes (4): Card, COLOR_HEX, Props, build_standard_deck()

### Community 145 - "Community 145"
Cohesion: 0.50
Nodes (4): getConfidenceLevel(), ObservationData, ObservationSummary(), Props

### Community 147 - "Community 147"
Cohesion: 0.40
Nodes (5): apply_action, create_initial_state, generate_legal_actions, uno-core, UnoCoreClient

### Community 148 - "Community 148"
Cohesion: 0.67
Nodes (4): appendPath(), getS3LikeProviderBaseUrl(), s3Url(), spacesUrl()

### Community 149 - "Community 149"
Cohesion: 0.50
Nodes (3): compileList(), compileMap(), Schema$1()

### Community 150 - "Community 150"
Cohesion: 0.67
Nodes (4): constructYamlTimestamp(), resolveYamlTimestamp(), YAML_DATE_REGEXP, YAML_TIMESTAMP_REGEXP

### Community 154 - "Community 154"
Cohesion: 0.50
Nodes (4): win, artifactName, icon, target

### Community 155 - "Community 155"
Cohesion: 0.83
Nodes (3): capture(), main(), Path

### Community 157 - "Community 157"
Cohesion: 0.67
Nodes (3): main(), pp(), End-to-end trace for web attach diagnostics on one fresh session.

### Community 158 - "Community 158"
Cohesion: 0.67
Nodes (3): main(), parse_args(), Namespace

### Community 159 - "Community 159"
Cohesion: 0.50
Nodes (4): infer_legacy(), InferenceRequest, InferenceResponse, Legacy endpoint — prefer /invoke.

### Community 164 - "Community 164"
Cohesion: 0.67
Nodes (3): ModelManifest, ModelRegistryClient, model-registry-service

### Community 165 - "Community 165"
Cohesion: 0.67
Nodes (3): Control Center, dev-backend.ps1, Local Development

## Knowledge Gaps
- **314 isolated node(s):** `require$$1`, `path$n`, `fs$j`, `require$$0`, `require$$0$1` (+309 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **47 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load()` connect `Community 62` to `Electron Bundle: Lodash Utils`, `Control Center: Tab/Window Pickers`, `Electron Bundle: Anchor/Parser Utils`?**
  _High betweenness centrality (0.315) - this node is a cross-community bridge._
- **Why does `WindowsRpaPanel()` connect `Community 62` to `Control Center: Operator Panel`?**
  _High betweenness centrality (0.176) - this node is a cross-community bridge._
- **Why does `build_summary()` connect `Profile Health Monitoring` to `Control Center: Tab/Window Pickers`, `Community 27`?**
  _High betweenness centrality (0.155) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `SessionOrchestrator` (e.g. with `run_e2e_trace()` and `main()`) actually correct?**
  _`SessionOrchestrator` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `ServiceClients` (e.g. with `FlowController` and `LowConfidenceError`) actually correct?**
  _`ServiceClients` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `PlaywrightSession` (e.g. with `PlaywrightWebAdapter` and `.__init__()`) actually correct?**
  _`PlaywrightSession` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `require$$1`, `path$n`, `fs$j` to the rest of the system?**
  _314 weakly-connected nodes found - possible documentation gaps or missing edges._