import torch
import torch.nn as nn
import torch.optim as optim
from PIL import Image
import torchvision.transforms as transforms
import torchvision.models as models


def load_image(img, max_size=512, shape=None):
    transform = transforms.Compose([
        transforms.Resize(max_size),
        transforms.ToTensor()
    ])
    image = transform(img)[:3, :, :].unsqueeze(0)
    if shape:
        image = transforms.Resize(shape)(image)
    return image


def gram_matrix(tensor):
    _, n_filters, h, w = tensor.size()
    t = tensor.view(n_filters, h * w)
    gram = torch.mm(t, t.t())
    return gram


class StyleTransferModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.vgg = models.vgg19(weights=models.VGG19_Weights.DEFAULT).features.eval()
        self.style_layers = ['0', '5', '10', '19', '28']
        self.content_layers = ['21']

        for param in self.vgg.parameters():
            param.requires_grad = False

    def forward(self, x):
        features = {}
        for name, layer in self.vgg._modules.items():
            x = layer(x)
            if name in self.style_layers + self.content_layers:
                features[name] = x
        return features


def run_style_transfer(content_img, style_img, num_steps=200, style_weight=1e6, content_weight=1):
    device = torch.device("cpu")

    content = load_image(content_img).to(device)
    style = load_image(style_img, shape=[content.size(2), content.size(3)]).to(device)
    generated = content.clone().requires_grad_(True)

    model = StyleTransferModel().to(device)
    optimizer = optim.Adam([generated], lr=0.02)

    style_features = model(style)
    content_features = model(content)
    style_grams = {layer: gram_matrix(style_features[layer]) for layer in model.style_layers}

    for step in range(num_steps):
        generated_features = model(generated)

        content_loss = torch.mean((generated_features['21'] - content_features['21']) ** 2)

        style_loss = 0
        for layer in model.style_layers:
            gen_feature = generated_features[layer]
            gen_gram = gram_matrix(gen_feature)
            style_gram = style_grams[layer]
            layer_loss = torch.mean((gen_gram - style_gram) ** 2)
            style_loss += layer_loss

        total_loss = content_weight * content_loss + style_weight * style_loss

        optimizer.zero_grad()
        total_loss.backward()
        optimizer.step()

    final_img = generated.cpu().clone().squeeze(0)
    final_img = transforms.ToPILImage()(final_img)

    return final_img
