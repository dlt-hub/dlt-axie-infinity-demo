# requires pyYAML
import os
import yaml
import re
import argparse
import base64
from pathlib import Path
from typing import Any, Dict, List

parser = argparse.ArgumentParser(
    description=
    "Extracts value from config maps, secrets and few other kinds of elements and places them into Helm value.yaml"
)
parser.add_argument("helmdir",
                    metavar="helm-root-dir",
                    type=str,
                    help="Root directory with the Helm generated with kompose")

args = parser.parse_args()

values: Dict[str, Dict[str, Any]] = {"secrets": {}, "pods": {}, "envs": {}, "volumes": {}, "images": {}}
pod_info_envs = yaml.safe_load("""
env:
  - name: KUBE_NODE_NAME
    valueFrom:
      fieldRef:
        fieldPath: spec.nodeName
  - name: KUBE_POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: KUBE_POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
""")


def str_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    # format multiline strings as blocks with the exception of placeholders
    # that will be expanded as yaml
    if len(data.splitlines()) > 1 and "{{ toYaml" not in data:  # check for multiline string
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


def camel(s: str) -> str:
    # remove dots
    s = s.replace(".", "-")
    # make camel case
    parts = re.sub(r"(_|-)+", " ", s).split(" ")
    parts = [parts[0].lower()] + [s.title() for s in parts[1:]]
    return "".join(parts)


def gen_b64_value(group: str, k: str) -> str:
    return "{{ .Values.%s.%s | b64enc | default \"'\" }}" % (group, k)


def gen_value_2(group: str, k: str) -> str:
    return "{{ .Values.%s.%s }}" % (group, k)


def gen_value(group: str, sub: str, k: str, mod: str = "") -> str:
    return "{{ .Values.%s.%s.%s %s }}" % (group, sub, k, mod)


def extract_secret(secret: str, template: Dict[str, Any]) -> None:
    g = values["secrets"]
    data = template["data"]
    for k, v in list(data.items()):
        values_k = camel(k)
        # keep plain text in values
        g[values_k] = base64.b64decode(v).decode("utf-8")
        # and encode back in template
        data[k] = gen_b64_value(secret, values_k)


def extract_cfmap(cfmap: str, template: Dict[str, Any], kind: str) -> None:
    g = values["envs"].setdefault(cfmap, {})
    # print(template["data"])
    data = template["data"]
    for k, v in list(data.items()):
        values_k = camel(k)
        g[values_k] = v
        data[k] = gen_value("envs", cfmap, values_k, "| quote")


def copy_labels_metadata(metadata: Dict[str, Dict[str, str]]) -> None:
    a_labels: Dict[str, str] = {}
    if "annotations" in metadata:
        a_labels = {k:v for k, v in metadata["annotations"].items() if k.startswith("autopoiesis.")}
    if len(a_labels) > 0:
        labels = metadata.setdefault("labels")
        labels.update(a_labels)


def copy_labels(template: Dict[str, Any]) -> None:
    # copy autopoiesis annotation to labels
    copy_labels_metadata(template["metadata"])
    if "template" in template["spec"]:
        copy_labels_metadata(template["spec"]["template"]["metadata"])


def extract_image(image: str) -> str:    
    label = gen_value_2("images", "pipelineImage")
    values["images"]["pipelineImage"] = image

    return label


def extract_set(group: str, template: Dict[str, Any], kind: str) -> None:
    # print(template["spec"])
    spec = template["spec"]["template"]["spec"]
    # add termination period
    if "terminationGracePeriodSeconds" not in spec:
        spec["terminationGracePeriodSeconds"] = 320
    if "nodeSelector" not in spec:
        spec["nodeSelector"] = {}

    g = values["pods"].setdefault(group, {})

    g["terminationGracePeriodSeconds"] = spec["terminationGracePeriodSeconds"]
    spec["terminationGracePeriodSeconds"] = gen_value("pods", group, "terminationGracePeriodSeconds")
    # same node selector for all pods
    values["nodeSelector"] = spec["nodeSelector"]
    spec["nodeSelector"] = "\n{{ toYaml .Values.nodeSelector | indent 2 }}"

    # verify all envs and secrets in maps
    for c in spec["containers"]:
        # extract image
        c["image"] = extract_image(c["image"])
        for e in c["env"]:
            if "valueFrom" not in e:
                raise Exception(
                    f"Not all envs in {group} are in config maps: {e['name']}")
        # propagate pod info
        c["env"].extend(pod_info_envs["env"])


def extract_volume(group: str, template: Dict[str, Any], kind: str) -> None:
    spec = template["spec"]
    g = values["volumes"].setdefault(group, {})
    if "storageClassName" in spec:
        values["volumes"]["storageClassName"] = spec["storageClassName"]
        spec["storageClassName"] = gen_value_2("volumes", "storageClassName")
    if "accessModes" in spec:
        values["volumes"]["accessModes"] = spec["accessModes"]
        spec["accessModes"] = "\n{{ toYaml .Values.volumes.accessModes | indent 2 }}"

    if "resources" in spec and "requests" in spec[
            "resources"] and "storage" in spec["resources"]["requests"]:
        g["storage"] = spec["resources"]["requests"]["storage"]
        spec["resources"]["requests"]["storage"] = gen_value("volumes", group, "storage")


def get_group_name(file_path: str, kind: str) -> str:
    if kind == "Secret":
        return "secrets"

    parts = Path(file_path).stem.split("-")[:-1]
    if parts[0] in ["dev", "prod", "envs", "secrets"]:
        parts = parts[1:]
    if kind in ["Deployment", "DaemonSet"]:
        parts += ["pod"]
    return camel("-".join(parts))


try:
    yaml.add_representer(str, str_representer)

    relative_path = f"{args.helmdir}/templates"
    templates = [
        os.path.join(relative_path, e.name) for e in os.scandir(relative_path)
        if e.is_file()
    ]
    for file in templates:
        with open(file, "r") as f:
            template = yaml.safe_load(f)
            kind = template["kind"]
            group = get_group_name(file, kind)
            # print(file_name)
            if kind in ["ConfigMap"]:
                extract_cfmap(group, template, kind)
            elif kind in ["Secret"]:
                extract_secret(group, template)
            elif kind in ["Deployment", "DaemonSet"]:
                copy_labels(template)
                extract_set(group, template, kind)
            elif kind in ["Service"]:
                copy_labels(template)
            elif kind in ["PersistentVolumeClaim"]:
                extract_volume(group, template, kind)
            else:
                raise Exception(f"Don't know how to process {kind} in {file}")
        serialized = yaml.dump(template, indent=2)
        serialized = re.sub(r"'([\s\n]*?{{.+?}})'",
                            r"\1",
                            serialized,
                            flags=re.DOTALL)
        # print(serialized)
        with open(file, "w") as f:
            f.write(serialized)

    with open(f"{args.helmdir}/values.yaml", "w") as f:
        yaml.dump(values, f, indent=2)
except Exception as e:
    print("Error during execution")
    print(str(e))
    raise
    exit(-1)