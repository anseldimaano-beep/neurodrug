path = '/app/app/ml/predictor.py'
c = open(path).read()
if 'def load_checkpoint' not in c:
    c += '\n    def load_checkpoint(self, checkpoint_path):\n        import torch, os\n        if not os.path.exists(checkpoint_path):\n            raise FileNotFoundError(checkpoint_path)\n        ckpt = torch.load(checkpoint_path, map_location=self.device)\n        state = ckpt.get(\"model_state_dict\", ckpt)\n        self.model.load_state_dict(state)\n        self.model.eval()\n'
    open(path, 'w').write(c)
    print('patched')
else:
    print('already present')
