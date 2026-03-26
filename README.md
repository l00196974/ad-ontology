# huawei-ad-ontology
$env:NO_PROXY="127.0.0.1"; python -m src.pipeline.main run --config config/config.yaml --prompt game_analysis --input data/game_positive_input.csv --output data/game_positive_out.csv

1. 根目录 tools/python_pipeline
2. 准备config.ya