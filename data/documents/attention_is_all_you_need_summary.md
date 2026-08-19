# Transformer Architecture & Attention Mechanism Notes

## Overview
The Transformer architecture was introduced in the seminal 2017 paper *"Attention Is All You Need"* by Vaswani et al. Unlike recurrent neural networks (RNNs) and LSTMs that process tokens sequentially, the Transformer relies entirely on self-attention mechanisms to model global dependencies between input and output tokens in parallel.

## Key Components

### 1. Scaled Dot-Product Attention
Attention computation is calculated via queries ($Q$), keys ($K$), and values ($V$):
$$\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V$$
Scaling by $\sqrt{d_k}$ prevents the dot products from growing excessively large in high dimensions, which would push the softmax function into regions with dangerously small gradients.

### 2. Multi-Head Attention
Instead of performing a single attention function, Multi-Head Attention projects queries, keys, and values $h$ times with different learned linear projections. This allows the model to jointly attend to information from different representation subspaces at different positions.

### 3. Positional Encoding
Since Transformers contain no recurrence or convolution, order information must be injected. Sinusoidal positional encodings of varying frequencies are added to input embeddings:
- $PE_{(pos, 2i)} = \sin(pos / 10000^{2i/d_{\text{model}}})$
- $PE_{(pos, 2i+1)} = \cos(pos / 10000^{2i/d_{\text{model}}})$

### 4. Feed-Forward Networks & Residual Connections
Each sub-layer (Self-Attention and Feed-Forward) is enclosed by a residual connection followed by Layer Normalization:
$$\text{Output} = \text{LayerNorm}(x + \text{SubLayer}(x))$$

## Applications in Modern AI
Modern Large Language Models (LLMs) like LLaMA, Mistral, GPT-4, and Qwen are based on decoder-only Transformer variants, optimized for causal language modeling and autoregressive text generation.
