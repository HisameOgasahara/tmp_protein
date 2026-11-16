def create_model(settings, seed, template_mode=None):
    from rf3.inference_engines.rf3 import RF3InferenceEngine
    from rf3.model.layers.af3_diffusion_transformer import AttentionPairBiasDiffusion
    from rf3.model.layers.pairformer_layers import AttentionPairBiasPairformerDeepspeed

    model = RF3InferenceEngine(
        ckpt_path="rf3", **settings,
        triangle_attention_backend="vanilla", dense_attention_backend="vanilla",
        early_stopping_plddt_threshold=None, trainer_overrides={"precision": "32-true"}, seed=seed,
    )
    model.transform_overrides["p_provide_inter_molecule_distances"] = 0.0
    model.initialize()
    if template_mode:
        from benchmark import guard_template_pipeline
        model.pipeline = guard_template_pipeline(model.pipeline, template_mode)
    layers = [layer for layer in model.trainer.state["model"].modules()
              if isinstance(layer, (AttentionPairBiasPairformerDeepspeed, AttentionPairBiasDiffusion))]
    if not layers or any(layer.use_deepspeed_evo for layer in layers):
        raise RuntimeError("Expected native RF3 attention layers on T4.")
    for layer in layers:
        layer.force_bfloat16 = False
    return model
