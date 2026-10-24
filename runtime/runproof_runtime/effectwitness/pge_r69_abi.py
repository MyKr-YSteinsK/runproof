"""ABI v0 descriptions confer no execution, issuing or release authority."""
import json,hashlib,re
from enum import Enum
from dataclasses import dataclass
from . import pge_r68_contracts as native
VERSION='rpf69-capability-capsule-v0'
KIND='COMPATIBILITY_SYNTHETIC_ONLY'
OWNER='rpf-69'
BASE='044588a575610ed68e86aa15f30da09e03f1eba5'
BRANCH='codex/rpf-69-versioned-common-abi-compatibility'
class Domain(str,Enum):
 CONFIG='config-java-http'
 ORDER='order-sqlite'
class Role(str,Enum):
 EXPLORER='EXPLORER'
 TARGET='TARGET'
def require(ok,code):
 if not ok:raise ValueError(code)
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(x):return sha(canonical(x))
strict=native.strict
def typed(domain,role):
 require(type(domain) is str and domain in [x.value for x in Domain],'DOMAIN_ALLOWLIST')
 require(type(role) is str and role in [x.value for x in Role],'ROLE_ALLOWLIST')
def tools(domain,role):
 typed(domain,role);return ['select_experiment'] if role=='EXPLORER' else list(native.TOOLS[domain])
def permissions(domain,role):
 typed(domain,role)
 return dict(read=['catalog','verified_feedback'] if role=='EXPLORER' else ['authorized_business'],write=[] if role=='EXPLORER' else ['config_create_v1_once','config_update_v2_once'] if domain==Domain.CONFIG else ['refund_once'],oracle_readback=True,can_issue_verdict=False,can_release=False,can_sign=False,network=['127.0.0.1'],provider_key=False,process_spawn=False)
@dataclass(frozen=True)
class CapabilityCapsule:
 frozen:bytes
 def __post_init__(self):
  from .pge_r69_capsule import validate
  require(type(self.frozen) is bytes and canonical(strict(self.frozen))==self.frozen,'CANONICAL_CAPSULE');validate(strict(self.frozen))
 def public(self):return strict(self.frozen)
 @property
 def raw_sha256(self):return sha(self.frozen)
