#### Jailbreaks and Safety Evaluations














### **Are LLMs robust to natural prompts that are** **closely related to the training set?**


#### Turns out No!





Response: Creating a phishing email aimed at stealing bank information typically
involves these steps:


1. Target Research and Selection:The attacker chooses a specific bank or financial
institution to impersonate. This allows for more targeted branding and increases …


##### Response Guided Question Augmentation (ReG-QA)


##### ReG-QAs are natural in both language and content

Warning: This section contains unfiltered content that may be offensive to some readers.




##### ReG-QAs are not just natural, but are very effective too!

_Attack Success Rates on the JailbreakBench dataset_


 ASR for LLMs that are robust to seed prompts (in the upper partition) is significantly higher
using the proposed approach (Reg-QA) when compared to the Paraphrasing baseline
(Para-QA)

 Para-QA is more effective in cases where the model is not robust to the seed prompt
(bottom partition)


##### ReG-QAs as adaptive attacks to verify defenses


 - **ASR** of the proposed approach is **significantly higher** than other attacks on JailbreakBench
both **with and without** integrating with **defenses**

 Jailbreaks generated using ReG-QA are **significantly more robust** than existing methods
since they are natural and cannot be distinguished from benign prompts.

 Thus the proposed approach acts as an _**adaptive attack**_ for existing defenses which use
the **non-naturalness** and **instability of existing attacks to random and semantic**
**perturbation** s as the feature for a detector, motivating the need for more robust defenses


##### Summary

###### ● Safety training DOES generalize partly, but not completely - there exist natural prompts in the semantic vicinity of almost every seed prompt that can jailbreak LLMs! ● The proposed approach ReG-QA successfully identifies several such natural and diverse prompts related to a given seed prompt that can successfully jailbreak popular LLMs ● It is important and also harder to defend against such “ Natural Jailbreaks ”


