import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image
from tensorflow.keras import Model, layers
from tensorflow.keras.layers import Conv2D


def show_conv_kernels(
    model, layer_name=None, layer_index=None, max_cols=8, cmap="gray"
):
    """
    Mostra visualmente os filtros (kernels) aprendidos de qualquer camada Conv2D.

    Parâmetros:
    - model: modelo Keras treinado
    - layer_name: nome da camada convolucional (string)
    - layer_index: índice da camada convolucional (int)
    - max_cols: número máximo de colunas no grid
    - cmap: colormap usado se for 1 canal (default: gray)
    """
    # --- Seleciona a camada alvo ---
    if layer_name:
        layer = model.get_layer(layer_name)
    elif layer_index is not None:
        layer = [l for l in model.layers if isinstance(l, Conv2D)][layer_index]
    else:
        raise ValueError("Informe layer_name ou layer_index.")

    if not isinstance(layer, Conv2D):
        raise TypeError(f"A camada {layer.name} não é Conv2D.")

    # --- Obtém pesos (kernels) e bias ---
    weights, biases = layer.get_weights()
    kh, kw, in_ch, out_ch = weights.shape

    print(f"Camada: {layer.name}")
    print(
        f"Shape dos filtros: {weights.shape} (altura, largura, canais de entrada, nº de filtros)"
    )

    # --- Monta grid ---
    n_cols = min(max_cols, out_ch)
    n_rows = int(np.ceil(out_ch / n_cols))

    plt.figure(figsize=(1.8 * n_cols, 1.8 * n_rows))
    for i in range(out_ch):
        kernel = weights[:, :, :, i]
        # Normaliza cada filtro para [0,1]
        kmin, kmax = kernel.min(), kernel.max()
        if kmax > kmin:
            kernel_norm = (kernel - kmin) / (kmax - kmin)
        else:
            kernel_norm = kernel

        plt.subplot(n_rows, n_cols, i + 1)
        if in_ch == 1:
            plt.imshow(kernel_norm[:, :, 0], cmap=cmap)
        else:
            plt.imshow(kernel_norm)
        plt.axis("off")
        plt.title(f"{i}", fontsize=8)
    plt.suptitle(f"Filtros aprendidos — {layer.name}", fontsize=12, y=0.95)
    plt.tight_layout()
    plt.show()


def extract_feature_maps(model, x_sample, layer_name):
    """
    Retorna o feature map da camada 'layer_name' como (H, W, F).
    Aceita x_sample no formato (H,W,C) ou (1,H,W,C).
    """
    # garante batch dimension
    x = np.asarray(x_sample)
    if x.ndim == 3:  # (H,W,C) -> (1,H,W,C)
        x = x[None, ...]
    # obtém a camada
    layer = model.get_layer(layer_name)
    if not isinstance(layer, Conv2D):
        raise TypeError(
            f"A camada '{layer_name}' não é Conv2D (é {type(layer).__name__})."
        )
    # modelo para ativações
    act_model = Model(model.input, layer.output)
    act = act_model.predict(x, verbose=0)
    # act é (1,H',W',F) ou (1,H',W') se F==1
    fmap = act[0]
    if fmap.ndim == 2:
        fmap = fmap[..., None]  # (H',W') -> (H',W',1)
    return fmap  # (H', W', F)


def _minmax_uint8(arr):
    """Normaliza um array 2D para [0,255] uint8 usando min/max por canal."""
    a_min, a_max = float(arr.min()), float(arr.max())
    if a_max <= a_min:
        return np.zeros_like(arr, dtype=np.uint8)
    arr_n = (arr - a_min) / (a_max - a_min)
    return (arr_n * 255.0).astype(np.uint8)


def plot_feature_map(
    model, x_sample, layer_name, feature_index=0, cmap="gray", return_image=False
):
    """
    Plota UM feature map (canal) específico da camada 'layer_name'.
    - Reescalona o canal individualmente para [0,255] (uint8).
    - feature_index: índice do canal (0..F-1).
    """
    fmap = extract_feature_maps(model, x_sample, layer_name)  # (H,W,F)
    H, W, F = fmap.shape
    if not (0 <= feature_index < F):
        raise IndexError(f"feature_index fora do intervalo: 0..{F - 1}")
    ch = fmap[:, :, feature_index]
    img_u8 = _minmax_uint8(ch)

    plt.figure(figsize=(4, 4))
    plt.imshow(img_u8, cmap=cmap, vmin=0, vmax=255)
    plt.axis("off")
    plt.title(f"{layer_name} · ch {feature_index}  |  shape=({H},{W})")
    plt.show()
    return img_u8 if return_image else None


def plot_feature_maps_grid(
    model, x_sample, layer_name, max_features=16, cols=8, cmap="gray"
):
    """
    Plota VÁRIOS canais em grid, cada um reescalonado de forma independente para [0,255].
    """
    fmap = extract_feature_maps(model, x_sample, layer_name)  # (H,W,F)
    H, W, F = fmap.shape
    n = int(min(F, max_features))
    rows = int(np.ceil(n / cols))

    fig, axes = plt.subplots(
        rows, cols, figsize=(2.0 * cols, 2.0 * rows), squeeze=False
    )
    for i, ax in enumerate(axes.flat[:n]):
        img_u8 = _minmax_uint8(fmap[:, :, i])
        ax.imshow(img_u8, cmap=cmap, vmin=0, vmax=255)
        ax.set_axis_off()
        ax.set_title(f"ch {i}", fontsize=8)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    fig.suptitle(
        f"{layer_name}  |  feature maps: {n}/{F}  |  each rescaled 0–255", y=0.98
    )
    plt.tight_layout()
    plt.show()


# --- 🔍 Busca automática da última Conv2D ---
def find_last_conv_layer(model):
    for layer in reversed(model.layers):
        if isinstance(layer, layers.Conv2D):
            return layer.name
    raise ValueError("Modelo não possui camada Conv2D.")


# --- 🔥 Grad-CAM Heatmap ---
def make_gradcam_heatmap(model, img_batch, class_index=None, last_conv_name=None):
    """
    img_batch: shape (1, H, W, C)
    class_index: índice da classe alvo; se None e a saída tem 1 neurônio (binário), usa 0
    """
    if last_conv_name is None:
        last_conv_name = find_last_conv_layer(model)
    last_conv_layer = model.get_layer(last_conv_name)

    grad_model = tf.keras.models.Model(
        [model.inputs], [last_conv_layer.output, model.output]
    )

    with tf.GradientTape() as tape:
        conv_outputs, predictions = grad_model(img_batch)
        if predictions.shape[-1] == 1:
            class_channel = predictions[:, 0]
        else:
            if class_index is None:
                class_index = tf.argmax(predictions[0])
            class_channel = predictions[:, class_index]

    grads = tape.gradient(class_channel, conv_outputs)
    pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))
    conv_outputs = conv_outputs[0]
    heatmap = tf.reduce_sum(tf.multiply(conv_outputs, pooled_grads), axis=-1)

    # Normaliza para [0,1]
    heatmap = tf.maximum(heatmap, 0) / tf.reduce_max(heatmap + 1e-8)
    return heatmap.numpy()


# --- 🎨 Mapa de cores branco→vermelho ---
WHITE_TO_RED = LinearSegmentedColormap.from_list(
    "white_to_red", ["#FFFFFF", "#FFE5E5", "#FF9A9A", "#CC0000"]
)


# --- 📸 Overlay bonito e sem OpenCV ---
def overlay_heatmap_on_image(heatmap, image, alpha=0.4, tau=0.15, gamma=1.0):
    """
    image: (H, W, C) em [0,1] ou [0,255]
    heatmap: (H', W') em [0,1]
    """

    def to_uint8_rgb(img):
        arr = np.asarray(img)
        if arr.ndim == 2:
            arr = arr[..., None]
        if arr.shape[-1] == 1:
            arr = np.repeat(arr, 3, axis=-1)
        if arr.dtype != np.uint8:
            arr = (
                (np.clip(arr, 0, 1) * 255).astype(np.uint8)
                if arr.max() <= 1.0
                else np.clip(arr, 0, 255).astype(np.uint8)
            )
        return arr

    base = to_uint8_rgb(image)
    H, W = base.shape[:2]

    # Ajustes de contraste e limiar
    hm = np.clip(heatmap, 0, 1).astype(np.float32)
    hm = np.where(hm < tau, 0.0, (hm - tau) / (1e-8 + 1 - tau))
    if gamma != 1.0:
        hm = hm**gamma

    # Resize + colormap branco→vermelho
    colored = (WHITE_TO_RED(hm)[..., :3] * 255).astype(np.uint8)
    colored = np.array(Image.fromarray(colored).resize((W, H), Image.BILINEAR))

    # Overlay
    out = base.astype(np.float32) * (1 - alpha * hm[..., None]) + colored.astype(
        np.float32
    ) * (alpha * hm[..., None])
    return np.clip(out, 0, 255).astype(np.uint8)


def eval_map(cnn, image):
    image_scaled = image / 255.0
    input_batch = image_scaled[None, ...]

    last_conv = find_last_conv_layer(cnn)
    heatmap = make_gradcam_heatmap(cnn, input_batch, last_conv_name=last_conv)
    overlay = overlay_heatmap_on_image(
        heatmap, image_scaled, alpha=0.5, tau=0.2, gamma=1.2
    )

    # --- Mostrar ---
    plt.figure(figsize=(10, 4))
    plt.subplot(1, 3, 1)
    plt.imshow(image_scaled.squeeze(), cmap="gray")
    plt.title("Imagem")
    plt.axis("off")
    plt.subplot(1, 3, 2)
    plt.imshow(heatmap, cmap=WHITE_TO_RED)
    plt.title("Heatmap")
    plt.axis("off")
    plt.subplot(1, 3, 3)
    plt.imshow(overlay)
    plt.title(f"Overlay ({last_conv})")
    plt.axis("off")
    plt.tight_layout()
    plt.show()
