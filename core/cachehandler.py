"""
cache_handler.py

Functions to help with loading and generating caches of model runs
given certain parameters.

This should work hand-in-hand with CachedServer to allow users to view
these cached runs, without using large amounts of server resources by
generating new data per user.
"""

import pickle

import tqdm

from core import model
from core import settingsloader

run_settings = [
    # settings for each individual run to create a cache for.
    # name: having a "Default" run is required
    #   - all names have to be unique
    # max_steps: required, and ignore whatever is in settings.ini
    # settings: change the defaults set in settings.ini, per run
    #   - any settings that are not in settings.ini are ignored
    {
        "name": "Balanced",
        "description": """<h5>Press the play button on the right of the titlebar to start the simulation.</h5>
        <p>This dataset runs the simulation with the default model settings,
        viewable in <i>settings</i>.</p><p>The agent fractions have been selected to be a good balance of what
        could be expected in a real system. For more information about what the actors represent, read the
        <i>About</i> section.</p>""",
        "max_steps": 1000,
        "settings": {
            "Model": {
                'num_agents': 100
            }
        }
    },
    {
        "name": "High number of bankers",
        "description": """<p>This dataset highlights how the amount of bankers affects volatility
        and the nomin supply.</p><p>The collateralisation ratio is based on demand for nomins.
        Bankers are the only agent at the moment who issue nomins regularly.</p>""",
        "max_steps": 1000,
        "settings": {
            "Model": {
                'num_agents': 125,
            },
            "Agents": {
                "AgentFractions": {
                    "Banker": 100
                }
            }
        }
    },
    {
        "name": "Many random actors",
        "description": """<p>This noisy dataset that examines how well the price stays at 1
        even with many actors behaving irrationally (or arationally).</p>""",
        "max_steps": 1000,
        "settings": {
            "Model": {
                'num_agents': 125,
            },
            "Agents": {
                "AgentFractions": {
                    "Randomizer": 100
                }
            }
        }
    },
    {
        "name": "Minimal",
        "description": """<p>This dataset contains a single member of each market player
        type that exists in the system. This highlights how they interact with each other.</p>""",
        "max_steps": 1000,
        "settings": {
            "Model": {
                'num_agents': 0,
            },
            "Agents": {
                'agent_minimum': 1
            }
        }
    },
    {
        "name": "Low number of Nomin Shorters",
        "description": """<p>This dataset removes a lot of the price control the nomin shorters bring,
        to see how well the price stays at 1 without the user expectation that the price would be near 1.</p>
        <p>This will show whether controlling the supply is enough to keep the price stable.</p>""",
        "max_steps": 1000,
        "settings": {
            "Model": {
                'num_agents': 125,
            },
            "Agents": {
                "AgentFractions": {
                    "NominShorter": 0,
                    "HavvenEscrowNominShorter": 0
                }
            }
        }
    },
]


def set_run_settings(defaults, run_settings):
    settings = {}

    for item in defaults:
        if item not in run_settings:
            settings[item] = defaults[item]
        elif type(defaults[item]) == dict:
            settings[item] = set_run_settings(defaults[item], run_settings[item])
        else:
            # this doesn't check type, assumes it is correct (as it is set in the code above)
            settings[item] = run_settings[item]
    return settings


def generate_new_caches(data):
    """
    generate a new dataset for each dataset that doesn't already exist in data

    overwrites the defined default settings for every run

    generate visualisation results for every step up to max_steps, and save it to 'result'

    store the result in the format:
      data["name"] = {"data": result, "settings": settings, "max_steps": max_steps}
    """
    from core.server import get_vis_elements

    for n, item in enumerate(run_settings):
        if item["name"] in data and len(data[item['name']]['data']) == item['max_steps']:
            print("already have:", item['name'])
            continue
        print("\nGenerating", item["name"])
        result = []
        settings = settingsloader.get_defaults()

        settings = set_run_settings(settings, item['settings'])

        model_settings = settings['Model']
        model_settings['agent_fractions'] = settings['Agents']['AgentFractions']

        havven_model = model.HavvenModel(
            model_settings,
            settings['Fees'],
            settings['Agents'],
            settings['Havven'],
            settings['Mint']
        )
        vis_elements = get_vis_elements()

        # # The following is for running the loop without tqdm for profiling
        # # As when profiling the model, tqdm shows up as ~17% runtime
        # for i in range(item["max_steps"]):
        #     if not i % 100:
        #         print(f"{n+1}/{len(run_settings)} [{'='*(i//100)}{'-'*(item['max_steps']//100 - i//100)}" +
        #               f"] {i}/{item['max_steps']}")

        for i in tqdm.tqdm(range(item["max_steps"])):
            havven_model.step()
            step_data = []
            for element in vis_elements:
                if i == 0:
                    if hasattr(element, "sent_data"):
                        element.sent_data = False
                        element_data = element.render(havven_model)
                    else:
                        element_data = element.render(havven_model)
                else:
                    element_data = element.render(havven_model)
                step_data.append(element_data)

            result.append(step_data)
        data[item["name"]] = {
            "data": result,
            "settings": settings,
            "max_steps": item["max_steps"],
            "description": item["description"]
        }
    return data


def load_saved():
    try:
        with open("./cache_data.pkl", 'rb') as f:
            print("Loading from cache_data.pkl...")
            data = pickle.load(f)
    except IOError:
        data = {}
    except EOFError:
        data = {}
    return data


def save_data(data):
    """overwrite existing cache file with the presented data"""
    with open("./cache_data.pkl", "wb") as f:
        pickle.dump(data, f)
    print("Caches saved to cache_data.pkl")
