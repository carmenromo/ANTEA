import numpy  as np
import pandas as pd

from . mctrue_functions import find_hits_of_given_particles

from typing import Sequence, Tuple


def lower_or_equal(f1: float, f2: float, allowed_error: float = 1.e-6) -> bool:
    return f1 <= f2 + allowed_error


def greater_or_equal(f1: float, f2: float, allowed_error: float = 1.e-6) -> bool:
    return f1 >= f2 - allowed_error


def from_cartesian_to_cyl(pos: Sequence[np.array]) -> Sequence[np.array]:
    cyl_pos = np.array([np.sqrt(pos[:,0]**2+pos[:,1]**2), np.arctan2(pos[:,1], pos[:,0]), pos[:,2]]).transpose()
    return cyl_pos


def phi_mean_var(pos_phi: Sequence[float], q: Sequence[float]) -> float:
    diff_sign = min(pos_phi ) < 0 < max(pos_phi)
    if diff_sign & (np.abs(np.min(pos_phi))>np.pi/2):
        pos_phi[pos_phi<0] = np.pi + np.pi + pos_phi[pos_phi<0]
    mean_phi = np.average(pos_phi, weights=q)
    var_phi  = np.average((pos_phi-mean_phi)**2, weights=q)

    return mean_phi, var_phi


def find_SiPMs_over_threshold(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """
    Integrate the charge in time of each SiPM and select only those with total
    charge larger than threshold.
    """
    tot_charges_df = df.groupby(['event_id','sensor_id'])[['charge']].sum()
    return tot_charges_df[tot_charges_df.charge > threshold].reset_index()


def find_closest_sipm(point: Tuple[float, float, float], sipms: pd.DataFrame) -> pd.DataFrame:
   """
   Find the closest SiPM to a point, given a df of SiPMs.
   """
   sns_positions = np.array([sipms.X.values, sipms.Y.values, sipms.Z.values]).transpose()

   subtr        = np.subtract(point, sns_positions)
   distances    = [np.linalg.norm(d) for d in subtr]
   min_dist     = np.min(distances)
   min_sipm     = np.isclose(distances, min_dist)
   closest_sipm = sipms[min_sipm]

   return closest_sipm


def divide_sipms_in_two_emispheres(sns_positions: Sequence[Tuple[float, float, float]], sns_charges: Sequence[float], reference_pos: Tuple[float, float, float]) -> Tuple[Sequence[float], Sequence[float], Sequence[Tuple[float, float, float]], Sequence[Tuple[float, float, float]]]:
    """
    Divide the SiPMs with charge between two emispheres, using a given reference direction (reference_pos) as
    a discriminator.
    Return the lists of the charges and the positions of the SiPMs of the two groups.
    """

    q1, q2     = [], []
    pos1, pos2 = [], []
    for sns_pos, charge in zip(sns_positions, sns_charges):
        scalar_prod = sns_pos.dot(reference_pos)
        if scalar_prod > 0.:
            q1.append(charge)
            pos1.append(sns_pos)
        else:
            q2.append(charge)
            pos2.append(sns_pos)

    return pos1, pos2, np.array(q1), np.array(q2)



def assign_sipms_to_gammas(sns_response: pd.DataFrame, true_pos: Sequence[Tuple[float, float, float]], DataSiPM_idx: pd.DataFrame) -> Tuple[Sequence[float], Sequence[float], Sequence[Tuple[float, float, float]], Sequence[Tuple[float, float, float]]]:
    """
    Divide the SiPMs with charge between the two back-to-back gammas,
    or to one of the two if the other one hasn't interacted.
    Return the lists of the charges and the positions of the SiPMs of the two groups.
    """
    sipms           = DataSiPM_idx.loc[sns_response.sensor_id]
    sns_closest_pos = [np.array([find_closest_sipm(pos, sipms).X.values, find_closest_sipm(pos, sipms).Y.values, find_closest_sipm(pos, sipms).Z.values]).transpose()[0] for pos in true_pos]

    q1, q2     = [], []
    pos1, pos2 = [], []

    sns_positions = np.array([sipms.X.values, sipms.Y.values, sipms.Z.values]).transpose()
    sns_charges   = sns_response.charge
    closest_pos   = sns_closest_pos[0] ## Look at the first one, which always exists.
    ### The sensors on the same semisphere are grouped together,
    ### and those on the opposite side, too, only
    ### if two interactions have been detected.
    for sns_pos, charge in zip(sns_positions, sns_charges):
        scalar_prod = sns_pos.dot(closest_pos)
        if scalar_prod > 0.:
            q1.append(charge)
            pos1.append(sns_pos)
        elif len(sns_closest_pos) == 2:
            q2.append(charge)
            pos2.append(sns_pos)

    return q1, q2, pos1, pos2


def select_coincidences(sns_response: pd.DataFrame, charge_range: Tuple[float, float], DataSiPM_idx: pd.DataFrame,
                        particles: pd.DataFrame, hits: pd.DataFrame)-> Tuple[Sequence[float], Sequence[float],
                                                                             Sequence[Tuple[float, float, float]],
                                                                             Sequence[Tuple[float, float, float]],
                                                                             Tuple[float, float, float],
                                                                             Tuple[float, float, float]]:
    """
    Find the SiPM with maximum charge. The set of sensors around it are labelled as 1.
    The sensors on the opposite emisphere are labelled as 2.
    The true position of the first gamma interaction is also returned for each emisphere.
    A range of charge is given to select singles in the photoelectric peak.
    """
    max_sns = sns_response[sns_response.charge == sns_response.charge.max()]
    ## If by chance two sensors have the maximum charge, choose one (arbitrarily)
    if len(max_sns != 1):
        max_sns = max_sns[max_sns.sensor_id == max_sns.sensor_id.min()]
    max_sipm = DataSiPM_idx.loc[max_sns.sensor_id]
    max_pos  = np.array([max_sipm.X.values, max_sipm.Y.values, max_sipm.Z.values]).transpose()[0]

    sipms         = DataSiPM_idx.loc[sns_response.sensor_id]
    sns_positions = np.array([sipms.X.values, sipms.Y.values, sipms.Z.values]).transpose()
    sns_charges   = sns_response.charge

    pos1, pos2, q1, q2 = divide_sipms_in_two_emispheres(sns_positions, sns_charges, max_pos)

    tot_q1 = sum(q1)
    tot_q2 = sum(q2)

    sel1 = (tot_q1 > charge_range[0]) & (tot_q1 < charge_range[1])
    sel2 = (tot_q2 > charge_range[0]) & (tot_q2 < charge_range[1])
    if not sel1 or not sel2:
        return [], [], [], [], None, None

    ### select electrons, primary gammas daughters
    sel_volume   = (particles.initial_volume == 'ACTIVE') & (particles.final_volume == 'ACTIVE')
    sel_name     = particles.name == 'e-'
    sel_vol_name = particles[sel_volume & sel_name]

    primaries = particles[particles.primary == True]
    sel_all   = sel_vol_name[sel_vol_name.mother_id.isin(primaries.particle_id.values)]
    if len(sel_all) == 0:
        return [], [], [], [], None, None
    ### Calculate the minimum time among the daughters of a given primary gamma
    min_t1 = min_t2 = -1
    gamma_pos1, gamma_pos2 = None, None
    if len(sel_all[sel_all.mother_id == 1]) > 0:
        min_t1   = sel_all[sel_all.mother_id == 1].initial_t.min()
        part_id  = sel_all[(sel_all.mother_id == 1) & (sel_all.initial_t == min_t1)].particle_id.values

        sel_hits      = find_hits_of_given_particles(part_id, hits)
        hit_positions = np.array([sel_hits.x.values, sel_hits.y.values, sel_hits.z.values]).transpose()
        gamma_pos1    = np.average(hit_positions, axis=0, weights=sel_hits.energy)
    if len(sel_all[sel_all.mother_id == 2]) > 0:
        min_t2  = sel_all[sel_all.mother_id == 2].initial_t.min()
        part_id = sel_all[(sel_all.mother_id == 2) & (sel_all.initial_t == min_t2)].particle_id.values

        sel_hits      = find_hits_of_given_particles(part_id, hits)
        hit_positions = np.array([sel_hits.x.values, sel_hits.y.values, sel_hits.z.values]).transpose()
        gamma_pos2    = np.average(hit_positions, axis=0, weights=sel_hits.energy)

    ### Calculate the minimum time among the hits of a given primary gamma
    if len(hits[hits.particle_id == 1]) > 0:
        g1_min = hits[hits.particle_id == 1].time.min()
        if min_t1 < 0 or g1_min < min_t1:
            min_t1    = g1_min
            g1_hit = hits[(hits.particle_id == 1) & (hits.time == g1_min)]
            gamma_pos1 = np.array([g1_hit.x.values, g1_hit.y.values, g1_hit.z.values]).transpose()[0]
    if len(hits[hits.particle_id == 2]) > 0:
        g2_min = hits[hits.particle_id == 2].time.min()
        if min_t2 < 0 or g2_min < min_t2:
            min_t2 = g2_min
            g2_hit = hits[(hits.particle_id == 2) & (hits.time == g2_min)]
            gamma_pos2 = np.array([g2_hit.x.values, g2_hit.y.values, g2_hit.z.values]).transpose()[0]

    if gamma_pos1 is None or gamma_pos2 is None:
        print("Cannot find two true gamma interactions for this event")
        return [], [], [], [], None, None

    true_pos1, true_pos2 = [], []
    scalar_prod = gamma_pos1.dot(max_pos)
    if scalar_prod > 0:
        true_pos1 = gamma_pos1
        true_pos2 = gamma_pos2
    else:
        true_pos1 = gamma_pos2
        true_pos2 = gamma_pos1


    return pos1, pos2, q1, q2, true_pos1, true_pos2
