// emacs -*- C++ -*-
#ifndef SUSY_WH_HTFFILLER_H
#define SUSY_WH_HTFFILLER_H

#include <string>
#include <vector>

class HistFitterTree;
namespace susy{ namespace wh { namespace kin { class DilepVars; } } }

namespace susy
{
namespace wh
{
/*!
  A class to feed the wh 2l variables to HistFitterTree
  
  davide.gerbaudo@gmail.com
  Jan 2014
*/
class HftFiller {
public:
    //! systematic variations of the weight that should be stored in the nominal tree
    struct WeightVariations {
        WeightVariations() { reset(); }
        WeightVariations& reset() {
            qflipUp_ = qflipDo_ = 1.0;
            elTrigUp_ = elTrigDo_ = 1.0;
            muTrigUp_ = muTrigDo_ = 1.0;
            elEffUp_ = elEffDo_ = 1.0;
            muEffUp_ = muEffDo_ = 1.0;
            bTagUp_ = bTagDo_ = 1.0;
            cTagUp_ = cTagDo_ = 1.0;
            lTagUp_ = lTagDo_ = 1.0;
            xsecUp_ = xsecDo_ = 1.0;
            mcgenUp_ = mcgenDo_ = 1.0;
            return *this;
        }
        float qflipUp_, qflipDo_;
        float elTrigUp_, elTrigDo_;
        float muTrigUp_, muTrigDo_;
        float elEffUp_, elEffDo_;
        float muEffUp_, muEffDo_;
        float bTagUp_, bTagDo_;
        float cTagUp_, cTagDo_;
        float lTagUp_, lTagDo_;
        float xsecUp_, xsecDo_;
        float mcgenUp_, mcgenDo_;
    };
public:
    HftFiller();
    ~HftFiller();
    bool init(const std::string &mcid, const std::vector<std::string> &systematics);
    bool close(float sumw);
    bool fill(size_t systIndex, const susy::wh::kin::DilepVars &v, unsigned int run, unsigned int event);
    bool fill(size_t systIndex, const susy::wh::kin::DilepVars &v, unsigned int run, unsigned int event, const WeightVariations &wv);
    size_t nTrees() const { return m_hftTrees.size(); }
    HftFiller& setOutputDir(const std::string dir);
    bool determineXsecUncertainty(const int dsid);
    float xsecRelativeUncertainty() const { return xsecRelativeUncertainty_; }
    bool determineMcGenUncertainty(const int dsid);
    float mcGenRelativeUncertainty(const int njet) const;
private:
    void assignDilepVars(HistFitterTree* const tree, const susy::wh::kin::DilepVars &v);
    void assignWeightVars(HistFitterTree* const tree, const susy::wh::HftFiller::WeightVariations &wv);
private: // rule of three 
    HftFiller(const HftFiller&);
    HftFiller& operator=(const HftFiller&);
private:
    std::vector<HistFitterTree*> m_hftTrees;
    std::string m_outdir;
    float xsecRelativeUncertainty_;
    float mcGenRelativeUncertainty1j_;
    float mcGenRelativeUncertainty23j_;
}; // end HftFiller

} // namespace wh
} // namespace susy

#endif // end include guard
